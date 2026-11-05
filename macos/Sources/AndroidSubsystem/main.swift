import AppKit

// One executable, three roles chosen by the bundle's Info.plist:
//   AndroidMode = install   the hidden APK installer that opens .apk files
//   AndroidPackage = <id>   a Mac app for one Android app (own Dock icon, only its window)
//   neither                 the Android Subsystem manager
let bundleInfo = Bundle.main.infoDictionary ?? [:]
if bundleInfo["AndroidMode"] as? String == "install" {
    MainActor.assumeIsolated { runInstaller() }
} else if let package = bundleInfo["AndroidPackage"] as? String {
    MainActor.assumeIsolated { runAndroidApp(package: package) }
} else {
    AndroidSubsystemApp.main()
}
