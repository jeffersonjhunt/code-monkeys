// xcwin — tiny window-server helper for apple-xcodebuild, compiled once on the Mac (swiftc -O).
//
//   xcwin preflight     prints "granted" or "denied": may this process capture the screen?
//                       Over SSH the grant belongs to /usr/libexec/sshd-keygen-wrapper.
//   xcwin window <pid>  prints the window number of <pid>'s largest on-screen normal window;
//                       exits 1 if it has none (without the grant, other apps' windows are hidden).
import CoreGraphics
import Foundation

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: xcwin preflight | xcwin window <pid>\n".data(using: .utf8)!)
    exit(2)
}

switch args[1] {
case "preflight":
    print(CGPreflightScreenCaptureAccess() ? "granted" : "denied")
case "window":
    guard args.count == 3, let pid = Int32(args[2]) else { exit(2) }
    let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements],
                                          kCGNullWindowID) as? [[String: Any]] ?? []
    var best: (id: Int, area: Double)? = nil
    for w in info {
        guard (w[kCGWindowOwnerPID as String] as? Int32) == pid,
              (w[kCGWindowLayer as String] as? Int) == 0,
              let id = w[kCGWindowNumber as String] as? Int,
              let b = w[kCGWindowBounds as String] as? [String: Double] else { continue }
        let area = (b["Width"] ?? 0) * (b["Height"] ?? 0)
        if best == nil || area > best!.area { best = (id, area) }
    }
    guard let found = best else { exit(1) }
    print(found.id)
default:
    exit(2)
}
