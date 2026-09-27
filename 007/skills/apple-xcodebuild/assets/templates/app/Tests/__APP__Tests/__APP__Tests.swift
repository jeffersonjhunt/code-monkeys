import Testing
@testable import __APP__

struct __APP__Tests {
    @Test func platformLineNamesThePlatform() {
        #if os(macOS)
        #expect(Greeting.platformLine == "Running on macOS")
        #else
        #expect(Greeting.platformLine == "Running on iOS")
        #endif
    }
}
