import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("__APP__")
                .font(.largeTitle.bold())
            Text(Greeting.platformLine)
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}

enum Greeting {
    static var platformLine: String {
        #if os(macOS)
        "Running on macOS"
        #else
        "Running on iOS"
        #endif
    }
}

#Preview {
    ContentView()
}
