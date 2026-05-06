import ApplicationServices
import Cocoa
import Darwin
import Foundation

private let observedNotifications: [CFString] = [
    kAXFocusedUIElementChangedNotification as CFString,
    kAXWindowCreatedNotification as CFString,
    kAXUIElementDestroyedNotification as CFString
]

private let actionableRoles: Set<String> = [
    kAXButtonRole as String,
    kAXTextFieldRole as String,
    kAXTextAreaRole as String,
    "AXLink",
    kAXCheckBoxRole as String
]

private struct ElementNode: Encodable {
    let id: String
    let role: String
    let title: String?
    let description: String?
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let centerX: Double
    let centerY: Double
    let focused: Bool
}

private struct StatePayload: Encodable {
    let type: String
    let reason: String
    let pid: pid_t
    let appName: String
    let bundleIdentifier: String?
    let timestamp: String
    let windowTitle: String?
    let elements: [ElementNode]
}

private struct ErrorPayload: Encodable {
    let type: String
    let message: String
    let timestamp: String
}

private final class AXTreeDaemon: NSObject {
    private let encoder = JSONEncoder()
    private var observer: AXObserver?
    private var observedAppElement: AXUIElement?
    private var observedPID: pid_t = 0
    private var debounceWorkItem: DispatchWorkItem?
    private let debounceInterval: TimeInterval = 0.300
    private let maxDepth = 64
    private let maxChildrenPerNode = 256
    private let maxVisitedNodes = 20_000

    override init() {
        encoder.dateEncodingStrategy = .iso8601
        super.init()
    }

    func run() {
        requireAccessibilityPermission()

        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(activeApplicationChanged(_:)),
            name: NSWorkspace.didActivateApplicationNotification,
            object: nil
        )

        attachToFrontmostApplication(reason: "startup")
        RunLoop.main.run()
    }

    @objc private func activeApplicationChanged(_ notification: Notification) {
        attachToFrontmostApplication(reason: "applicationActivated")
    }

    private func requireAccessibilityPermission() {
        let options = [
            kAXTrustedCheckOptionPrompt.takeRetainedValue() as String: true
        ] as CFDictionary

        guard AXIsProcessTrustedWithOptions(options) else {
            fputs(
                "Accessibility permission required. Grant access to this terminal or IDE in System Settings > Privacy & Security > Accessibility.\n",
                stderr
            )
            exit(2)
        }
    }

    private func attachToFrontmostApplication(reason: String) {
        guard let app = NSWorkspace.shared.frontmostApplication else {
            emitError("No frontmost application is available.")
            return
        }

        let pid = app.processIdentifier
        if pid == observedPID {
            scheduleSnapshot(reason: reason)
            return
        }

        detachCurrentObserver()

        let appElement = AXUIElementCreateApplication(pid)
        var newObserver: AXObserver?
        let createError = AXObserverCreate(pid, axObserverCallback, &newObserver)

        guard createError == .success, let createdObserver = newObserver else {
            emitError("Unable to create AXObserver for pid \(pid): \(createError).")
            scheduleSnapshot(reason: reason)
            return
        }

        let refcon = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        for notification in observedNotifications {
            let error = AXObserverAddNotification(createdObserver, appElement, notification, refcon)
            if error != .success && error != .notificationUnsupported {
                emitError("Unable to observe \(notification) for pid \(pid): \(error).")
            }
        }

        CFRunLoopAddSource(
            CFRunLoopGetMain(),
            AXObserverGetRunLoopSource(createdObserver),
            CFRunLoopMode.defaultMode
        )

        observer = createdObserver
        observedAppElement = appElement
        observedPID = pid
        scheduleSnapshot(reason: reason)
    }

    private func detachCurrentObserver() {
        debounceWorkItem?.cancel()
        debounceWorkItem = nil

        guard let existingObserver = observer else {
            observedAppElement = nil
            observedPID = 0
            return
        }

        CFRunLoopRemoveSource(
            CFRunLoopGetMain(),
            AXObserverGetRunLoopSource(existingObserver),
            CFRunLoopMode.defaultMode
        )
        observer = nil
        observedAppElement = nil
        observedPID = 0
    }

    fileprivate func handleAccessibilityNotification(_ notification: CFString) {
        scheduleSnapshot(reason: notification as String)
    }

    private func scheduleSnapshot(reason: String) {
        debounceWorkItem?.cancel()
        let workItem = DispatchWorkItem { [weak self] in
            self?.emitSettledState(reason: reason)
        }
        debounceWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + debounceInterval, execute: workItem)
    }

    private func emitSettledState(reason: String) {
        guard let app = NSWorkspace.shared.frontmostApplication else {
            emitError("No frontmost application is available.")
            return
        }

        let appElement = AXUIElementCreateApplication(app.processIdentifier)
        let window = focusedWindow(for: appElement) ?? firstWindow(for: appElement)

        guard let frontmostWindow = window else {
            let payload = StatePayload(
                type: "state",
                reason: reason,
                pid: app.processIdentifier,
                appName: app.localizedName ?? "Unknown",
                bundleIdentifier: app.bundleIdentifier,
                timestamp: isoTimestamp(),
                windowTitle: nil,
                elements: []
            )
            emitJSON(payload)
            return
        }

        var visitedCount = 0
        var elements: [ElementNode] = []
        walk(
            element: frontmostWindow,
            path: "0",
            depth: 0,
            elements: &elements,
            visitedCount: &visitedCount
        )

        let payload = StatePayload(
            type: "state",
            reason: reason,
            pid: app.processIdentifier,
            appName: app.localizedName ?? "Unknown",
            bundleIdentifier: app.bundleIdentifier,
            timestamp: isoTimestamp(),
            windowTitle: stringAttribute(frontmostWindow, kAXTitleAttribute as CFString),
            elements: elements
        )
        emitJSON(payload)
    }

    private func walk(
        element: AXUIElement,
        path: String,
        depth: Int,
        elements: inout [ElementNode],
        visitedCount: inout Int
    ) {
        guard depth <= maxDepth, visitedCount < maxVisitedNodes else {
            return
        }

        visitedCount += 1

        if let node = nodeIfActionable(element, path: path) {
            elements.append(node)
        }

        let children = arrayAttribute(element, kAXChildrenAttribute as CFString)
        for (index, child) in children.prefix(maxChildrenPerNode).enumerated() {
            walk(
                element: child,
                path: "\(path).\(index)",
                depth: depth + 1,
                elements: &elements,
                visitedCount: &visitedCount
            )
        }
    }

    private func nodeIfActionable(_ element: AXUIElement, path: String) -> ElementNode? {
        guard let role = stringAttribute(element, kAXRoleAttribute as CFString),
              actionableRoles.contains(role),
              let origin = pointAttribute(element, kAXPositionAttribute as CFString),
              let size = sizeAttribute(element, kAXSizeAttribute as CFString),
              size.width > 0,
              size.height > 0
        else {
            return nil
        }

        return ElementNode(
            id: path,
            role: role,
            title: normalizedText(stringAttribute(element, kAXTitleAttribute as CFString)),
            description: normalizedText(stringAttribute(element, kAXDescriptionAttribute as CFString)),
            x: rounded(origin.x),
            y: rounded(origin.y),
            width: rounded(size.width),
            height: rounded(size.height),
            centerX: rounded(origin.x + size.width / 2.0),
            centerY: rounded(origin.y + size.height / 2.0),
            focused: boolAttribute(element, kAXFocusedAttribute as CFString) ?? false
        )
    }

    private func focusedWindow(for appElement: AXUIElement) -> AXUIElement? {
        elementAttribute(appElement, kAXFocusedWindowAttribute as CFString)
    }

    private func firstWindow(for appElement: AXUIElement) -> AXUIElement? {
        arrayAttribute(appElement, kAXWindowsAttribute as CFString).first
    }

    private func stringAttribute(_ element: AXUIElement, _ attribute: CFString) -> String? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value
        else {
            return nil
        }

        if let string = unwrapped as? String {
            return string
        }

        return String(describing: unwrapped)
    }

    private func boolAttribute(_ element: AXUIElement, _ attribute: CFString) -> Bool? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value
        else {
            return nil
        }

        return unwrapped as? Bool
    }

    private func pointAttribute(_ element: AXUIElement, _ attribute: CFString) -> CGPoint? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value,
              CFGetTypeID(unwrapped) == AXValueGetTypeID()
        else {
            return nil
        }

        let axValue = unwrapped as! AXValue
        var point = CGPoint.zero
        guard AXValueGetValue(axValue, .cgPoint, &point) else {
            return nil
        }
        return point
    }

    private func sizeAttribute(_ element: AXUIElement, _ attribute: CFString) -> CGSize? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value,
              CFGetTypeID(unwrapped) == AXValueGetTypeID()
        else {
            return nil
        }

        let axValue = unwrapped as! AXValue
        var size = CGSize.zero
        guard AXValueGetValue(axValue, .cgSize, &size) else {
            return nil
        }
        return size
    }

    private func elementAttribute(_ element: AXUIElement, _ attribute: CFString) -> AXUIElement? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value
        else {
            return nil
        }

        return (unwrapped as! AXUIElement)
    }

    private func arrayAttribute(_ element: AXUIElement, _ attribute: CFString) -> [AXUIElement] {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success,
              let unwrapped = value
        else {
            return []
        }

        guard let array = unwrapped as? [AnyObject] else {
            return []
        }

        return array.compactMap { item in
            item as! AXUIElement?
        }
    }

    private func emitError(_ message: String) {
        let payload = ErrorPayload(
            type: "error",
            message: message,
            timestamp: isoTimestamp()
        )
        emitJSON(payload)
    }

    private func emitJSON<T: Encodable>(_ payload: T) {
        do {
            let data = try encoder.encode(payload)
            if let line = String(data: data, encoding: .utf8) {
                print(line)
                fflush(stdout)
            }
        } catch {
            fputs("Failed to encode JSON payload: \(error)\n", stderr)
        }
    }

    private func isoTimestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }

    private func normalizedText(_ text: String?) -> String? {
        guard let text else {
            return nil
        }

        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func rounded(_ value: CGFloat) -> Double {
        (Double(value) * 100.0).rounded() / 100.0
    }
}

private let axObserverCallback: AXObserverCallback = { _, _, notification, refcon in
    guard let refcon else {
        return
    }

    let daemon = Unmanaged<AXTreeDaemon>.fromOpaque(refcon).takeUnretainedValue()
    daemon.handleAccessibilityNotification(notification)
}

private let daemon = AXTreeDaemon()
daemon.run()
