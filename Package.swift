// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AXTreeAPI",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "axtree-daemon", targets: ["AXTreeDaemon"])
    ],
    targets: [
        .executableTarget(
            name: "AXTreeDaemon",
            path: "Sources/AXTreeDaemon",
            linkerSettings: [
                .linkedFramework("ApplicationServices"),
                .linkedFramework("Cocoa")
            ]
        )
    ]
)
