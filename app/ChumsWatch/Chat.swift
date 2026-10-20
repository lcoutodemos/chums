import SwiftUI

/// One line of the conversation: what you said, what Chums said, or a note (an approval answered, an action Claude
/// Code's auto mode refused).
struct ChatLine: Identifiable, Equatable {
    enum Who { case you, chums, note }
    let id: String
    let who: Who
    let text: String
    let artifact: Artifact?
    var refused = false                     // Claude Code's auto mode refused an action, without asking you

    init(_ s: Spoken) {
        id = s.id; artifact = s.artifact; refused = s.kind == "refused"
        switch s.kind {
        case "echo":
            who = .you
            // the hub echoes an order as “what you said” (with the session's name first when there are several)
            text = s.text.replacingOccurrences(of: "“", with: "").replacingOccurrences(of: "”", with: "")
        case "verdict", "refused": who = .note; text = s.text
        default: who = .chums; text = s.text
        }
    }
}

/// The conversation as a card of Liquid Glass that slides up from the handle at the bottom of the screen: the
/// character stays visible through it, blurred. It opens at the newest message; the crown scrolls back. Dragging its
/// top edge down puts it away. The balloons are nearly solid so the text reads over anything behind the glass.
struct ChatPanel: View {
    let lines: [ChatLine]
    var open: (Artifact) -> Void = { _ in }
    /// Simulator captures: scroll to a line (or "end"), as a finger would, over that many seconds.
    var scroll: (id: String, seconds: Double)? = nil
    @FocusState private var focused: Bool

    static let card = UnevenRoundedRectangle(topLeadingRadius: 22, topTrailingRadius: 22)

    var body: some View {
        // the messages fill the whole card and scroll all the way to its top edge; the grabber floats over them
        ZStack(alignment: .top) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 8) {
                        Color.clear.frame(height: 14).id("top")             // at rest, the first message starts below the grabber
                        if lines.isEmpty {
                            Text("Hold the screen and talk; the conversation shows up here.")
                                .font(.system(size: 14)).foregroundStyle(Pal.gray).multilineTextAlignment(.center).padding(.top, 16)
                        }
                        ForEach(lines) { l in bubble(l).id(l.id) }
                        Color.clear.frame(height: 6).id("end")
                    }
                    .padding(.horizontal, 6)
                }
                .focusable().focused($focused)
                .onAppear { proxy.scrollTo("end", anchor: .bottom); focused = true }
                .onChange(of: lines.count) { withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
                .onChange(of: scroll?.id) { _, id in
                    guard let id, let s = scroll else { return }
                    withAnimation(.easeInOut(duration: s.seconds)) { proxy.scrollTo(id, anchor: id == "end" ? .bottom : .top) }   // "top": the very start
                }
            }
            Grabber().padding(.top, 6)
        }
        .clipShape(Self.card)                                                // only the card's own edge clips
        .chumsGlass(tint: .black.opacity(0.32), in: Self.card)
    }

    @ViewBuilder private func bubble(_ l: ChatLine) -> some View {
        switch l.who {
        case .you:
            HStack {
                Spacer(minLength: 24)
                Text(l.text).font(.system(size: 15)).foregroundStyle(Pal.white).fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10).padding(.vertical, 7)
                    .background(Color(hex: 0x3A3D42).opacity(0.92), in: RoundedRectangle(cornerRadius: 14))
            }
        case .chums:
            VStack(alignment: .leading, spacing: 4) {
                if l.artifact.map({ $0.title != l.text }) ?? true {
                    HStack {
                        Text(l.text).font(.system(size: 15)).foregroundStyle(Pal.white).fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 10).padding(.vertical, 7)
                            .background(Color(white: 0.17).opacity(0.94), in: RoundedRectangle(cornerRadius: 14))
                        Spacer(minLength: 24)
                    }
                }
                // something it showed you: a pill that opens it
                if let a = l.artifact { ArtifactPill(a: a) { open(a) } }
            }
        case .note:
            Text(l.text).font(.system(size: 11, weight: .medium)).foregroundStyle(Pal.white.opacity(0.75)).frame(maxWidth: .infinity)
                .shadow(color: .black.opacity(0.6), radius: 2)
        }
    }
}

/// Simulator captures: what the scene driver asks screens it can't reach directly (the agents list, a soul) to do,
/// as a finger would: scroll to a row, pick an agent, open a soul, press and let go of its button, save.
@Observable final class Capture {
    static let shared = Capture()
    let touch = TouchShow()
    var listScroll: String?                     // a row of the agents list ("settings" for the Settings row)
    var pick: String?                           // an agent tapped in the list
    var openSoul: String?                       // its soul opened (the Edit in its row)
    var soulScroll: String?                     // "top" or "end"
    var soulPress: Bool?                        // the soul's hold-to-change button: pressed (true), let go (false)
    var soulSave = false                        // Save tapped
}

/// Simulator captures: where a finger is on the screen, drawn as a fingertip on the glass (a soft disc that presses in,
/// holds, slides and lifts off), so a recording shows what was touched.
@Observable final class TouchShow {
    var at: CGPoint = .zero
    var down = false
    var visible = false
}

struct TouchSpot: View {
    let show: TouchShow
    var body: some View {
        Circle()
            .fill(RadialGradient(colors: [.white.opacity(0.42), .white.opacity(0.22)], center: .center, startRadius: 0, endRadius: 17))
            .overlay(Circle().strokeBorder(.white.opacity(0.6), lineWidth: 1))
            .frame(width: 34, height: 34)
            .shadow(color: .black.opacity(0.35), radius: 5, y: 1)
            .scaleEffect(show.visible ? (show.down ? 0.92 : 1.0) : 1.35)
            .opacity(show.visible ? 1 : 0)
            .position(show.at)
            .animation(.easeOut(duration: 0.22), value: show.visible)
            .animation(.spring(duration: 0.25, bounce: 0.3), value: show.down)
            .allowsHitTesting(false)
    }
}

/// The handle: on the screen's bottom edge to pull the conversation up, and on the card's top edge to put it away.
struct Grabber: View {
    /// Under the character: gray and short, so it doesn't read as a mouth under the eyes.
    var quiet = false
    var body: some View {
        Capsule().fill(Color(white: quiet ? 0.4 : 0.86)).frame(width: quiet ? 28 : 46, height: quiet ? 4 : 5)
            .shadow(color: .black.opacity(0.45), radius: 1.5, y: 0.5)
    }
}
