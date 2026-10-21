// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "AndroidSubsystem",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "AndroidSubsystem", targets: ["AndroidSubsystem"])],
    targets: [.executableTarget(name: "AndroidSubsystem")]
)
