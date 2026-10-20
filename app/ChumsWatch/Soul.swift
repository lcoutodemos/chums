import SwiftUI

/// An agent, opened on the watch. What you can change about how it runs is in tiles at the top (what it runs on, its
/// model, its permissions, its voice: each opens a list). Its soul is the text under them: what it does, what it hands
/// off, how it talks, notes. At the bottom, hold the button and say what should be different: a separate model on the
/// Mac turns it into a change, shown in plain words; Save keeps it (it applies from the agent's next order), Cancel
/// drops it, Undo goes back one.
struct SoulView: View {
    let agent: AgentInfo
    let model: ScreenModel
    let hub: HubClient

    enum Step: Equatable { case card, listening, writing, preview, clarify(String), saving, saved, failed(String) }
    @State private var step = Step.card
    @State private var card: SoulCard?
    @State private var proposal: SoulProposal?
    @State private var slide = 0.0                                  // the finger's slide while talking: −1 × … 1 ✓
    @State private var pressing = false
    @State private var holdStart: Task<Void, Never>?

    var body: some View {
        // one scroll: read it, and at the end, change it
        ScrollViewReader { proxy in
        ScrollView {
            VStack(spacing: 8) {
                Color.clear.frame(height: 0).id("top")
                // who it is: its face and name
                HStack(spacing: 9) {
                    AgentFace(character: agent.character, size: 32)
                    Text(shown?.name ?? agent.name).font(.system(size: 18, weight: .semibold)).foregroundStyle(Pal.white)
                    Spacer(minLength: 0)
                }
                .padding(.leading, 4)
                // what you can change: each a tile that opens a list
                runtimeTile
                modelTile
                permissionTile
                voiceTile
                if let m = message { messageTile(m).padding(.top, 4) }
                // who it is: words on the page, no tiles
                if let c = shown {
                    VStack(alignment: .leading, spacing: 10) {
                        part("What it does", c.owns, changed: step == .preview && c.owns != card?.owns)
                        part("Hands off", c.refers, changed: step == .preview && c.refers != card?.refers)
                        part("How it talks", c.voice, changed: step == .preview && c.voice != card?.voice)
                        part("Notes", c.body, changed: step == .preview && c.body != card?.body, lines: 8)
                    }
                    .padding(.horizontal, 6).padding(.top, 8)
                } else { ProgressView().padding(.top, 8) }
                // at the bottom: change it, or take the last change back
                controls.padding(.top, 10)
                if card?.canUndo == true && (step == .card || step == .saved) {
                    Button { Task { await undo() } } label: {
                        Label("Undo last change", systemImage: "arrow.uturn.backward").font(.system(size: 14, weight: .medium))
                            .foregroundStyle(Pal.white).frame(maxWidth: .infinity, minHeight: 38)
                    }
                    .buttonStyle(.plain).chumsGlass(interactive: true, in: Capsule())
                }
                Color.clear.frame(height: 0).id("end")
            }
            .padding(.horizontal, 2)
        }
        // Simulator captures: the scene driver scrolls, holds the button and saves as a finger would
        .onChange(of: Capture.shared.soulScroll) { _, id in
            guard let id else { return }
            withAnimation(.easeInOut(duration: 1.1)) { proxy.scrollTo(id, anchor: id == "top" ? .top : .bottom) }
            Capture.shared.soulScroll = nil
        }
        .onChange(of: Capture.shared.soulPress) { _, down in
            guard let down else { return }
            Capture.shared.soulPress = nil
            if down {
                guard [Step.card, .saved].contains(step) || isMessage(step), model.startSoulTalk() else { return }
                pressing = true; step = .listening
            } else {
                pressing = false
                guard step == .listening else { return }
                slide = 0
                Task { await finishTalking(cancel: false) }
            }
        }
        .onChange(of: Capture.shared.soulSave) { _, on in
            guard on else { return }
            Capture.shared.soulSave = false
            Task { await save() }
        }
        }
        .defaultScrollAnchor(UserDefaults.standard.bool(forKey: "soulBottom") ? .bottom : .top)   // Simulator captures
        .opacity(step == .listening ? 0.2 : 1)
        .overlay { if step == .listening { TalkBar(slide: slide, level: { model.talkLevel }) } }
        .navigationTitle("Soul")
        .task {
            async let m = hub.models(), p = hub.permissions()
            (models, permissions) = await (m, p)
        }
        .task {
            card = await hub.soul(agent.id)
            // Simulator captures: a typed instruction instead of a spoken one (-soulSay "…")
            if let said = UserDefaults.standard.string(forKey: "soulSay"), step == .card {
                step = .writing
                if let r = await hub.soulFromText(said, agent: agent.id), r.proposal != nil { proposal = r; step = .preview }
                else { step = .card }
            }
        }
    }

    private var shown: SoulCard? { step == .preview ? proposal?.soul ?? card : card }

    /// What's going on, above the parts: the proposed change, a question back, saved, why it failed, or working on it.
    private var message: (text: String, color: Color, busy: Bool)? {
        switch step {
        case .preview: return (proposal?.summary ?? "", Pal.white, false)
        case .clarify(let q): return (q, Pal.amber, false)
        case .saved: return ("Saved. \(card?.name ?? agent.name) follows it from its next order.", Pal.white, false)
        case .failed(let why): return (why, Pal.red, false)
        case .writing: return ("Writing the change…", Pal.gray, true)
        case .saving: return ("Saving…", Pal.gray, true)
        default: return nil
        }
    }
    private func messageTile(_ m: (text: String, color: Color, busy: Bool)) -> some View {
        HStack(alignment: .top, spacing: 8) {
            if m.busy { ProgressView().frame(width: 16, height: 16) }
            Text(m.text).font(.system(size: 15, weight: .medium)).foregroundStyle(m.color).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(11)
        .chumsGlass(tint: .white.opacity(0.1), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    /// The characters, each its own agent, in the order the watch lists them first.
    static let looks = ["noodle", "squint", "ray", "tangle", "peeps", "stretch", "crunch", "nana"]

    /// A tile that opens a list: what it is, small, and its value under it.
    private func tile(_ title: String, _ value: String) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(Pal.gray)
                Text(value).font(.system(size: 14, weight: .medium)).foregroundStyle(Pal.white).lineLimit(1)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(Pal.gray)
        }
        .padding(.horizontal, 11).padding(.vertical, 9)
        .chumsGlass(in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    /// Its model and its permissions, as on the iPhone's card: a list for its runtime, its runtime's own setting first.
    @State private var models: [String: ModelChoices]?
    @State private var permissions: [String: PermissionChoices]?
    @State private var pickedModel: String??                 // picked here (until then, the hub's)
    @State private var pickedPermission: String??
    private var runtimeNow: String { runtime ?? agent.runtime ?? "claude" }
    private func named(_ id: String?, in items: [ModelChoices.Model]?, default d: String?) -> String {
        guard let items else { return " " }
        if let id { return items.first { $0.id == id }?.name ?? id }
        return d ?? "\(AgentRuntimes.name(runtimeNow))'s own"
    }
    private var modelTile: some View {
        let c = models?[runtimeNow], now = pickedModel ?? agent.model
        return NavigationLink {
            ChoiceList(title: "Model", items: c?.models, defaultLabel: c?.default, runtime: runtimeNow,
                       footer: "It restarts on the model you pick. Its conversation carries on.",
                       picked: Binding(get: { now }, set: { pickedModel = .some($0) })) { await hub.setModel(agent.id, model: $0) }
        } label: { tile("Model", named(now, in: c?.models, default: c?.default)) }
        .buttonStyle(.plain)
    }
    @State private var choosingPermission = UserDefaults.standard.bool(forKey: "openPermissions")   // Simulator captures
    private var permissionTile: some View {
        let c = permissions?[runtimeNow], now = pickedPermission ?? agent.permission
        return Button { choosingPermission = true } label: { tile("Permissions", named(now, in: c?.modes, default: c?.default)) }
            .buttonStyle(.plain)
            .navigationDestination(isPresented: $choosingPermission) {
                ChoiceList(title: "Permissions", items: c?.modes, defaultLabel: c?.default, runtime: runtimeNow,
                           footer: "It restarts with what you pick. Its conversation carries on.",
                           picked: Binding(get: { now }, set: { pickedPermission = .some($0) })) { await hub.setPermission(agent.id, mode: $0) }
            }
    }

    /// What it runs on, as a row like its voice: a tap opens the two to pick from (AgentRuntimes).
    @State private var runtime: String?
    @State private var choosingRuntime = UserDefaults.standard.bool(forKey: "openRuntimes")   // Simulator captures
    private var runtimeTile: some View {
        let current = runtime ?? agent.runtime ?? "claude"
        return Button { choosingRuntime = true } label: { tile("Runs on", AgentRuntimes.name(current)) }
        .buttonStyle(.plain)
        .accessibilityIdentifier("runtime-row")
        .navigationDestination(isPresented: $choosingRuntime) {
            AgentRuntimes(agent: agent, hub: hub, picked: Binding(get: { current }, set: { runtime = $0; pickedModel = nil; pickedPermission = nil }))
        }
    }

    /// Its voice on the Mac: a tap opens the voices (each plays a sample, a tap picks it).
    @State private var voice: String?
    private var voiceTile: some View {
        let id = voice ?? agent.voice
        return NavigationLink {
            AgentVoices(agent: agent, hub: hub, picked: Binding(get: { voice ?? agent.voice }, set: { voice = $0 }))
        } label: { tile("Voice", id.map(AgentVoices.label) ?? "The watch's own") }
        .buttonStyle(.plain)
    }

    /// One part of the soul, as words on the page: its name small, the words under it; a part a change would touch is
    /// white, with a mark beside its name.
    @ViewBuilder private func part(_ label: String, _ value: String?, changed: Bool, lines: Int? = nil) -> some View {
        if let value, !value.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(label).font(.system(size: 11, weight: .semibold)).foregroundStyle(changed ? Pal.white : Pal.gray)
                    if changed { Circle().fill(Pal.white).frame(width: 4, height: 4) }
                }
                Text(value).font(.system(size: 15)).foregroundStyle(changed ? Pal.white : Color(white: 0.85))
                    .lineLimit(lines).fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
        }
    }

    /// Save and Cancel for a proposed change; otherwise the button you hold to talk (× and ✓ show above your finger).
    @ViewBuilder private var controls: some View {
        if step == .preview {
            HStack(spacing: 8) {
                Button { Haptics.play(.click); proposal = nil; step = .card } label: {
                    Text("Cancel").font(.system(size: 15, weight: .semibold)).foregroundStyle(Pal.white).frame(maxWidth: .infinity, minHeight: 40)
                }
                .buttonStyle(.plain).chumsGlass(interactive: true, in: Capsule())
                Button { Task { await save() } } label: {
                    Text("Save").font(.system(size: 15, weight: .semibold)).foregroundStyle(.black).frame(maxWidth: .infinity, minHeight: 40)
                }
                .buttonStyle(.plain).chumsGlass(tint: .white, interactive: true, in: Capsule())
            }
        } else {
            HStack(spacing: 7) {
                Image(systemName: "mic.fill").font(.system(size: 13, weight: .semibold))
                Text("Hold to change").font(.system(size: 15, weight: .semibold))
            }
            .foregroundStyle(Pal.white).opacity(step == .listening ? 0 : 1)
            .frame(maxWidth: .infinity, minHeight: 42)
            .chumsGlass(tint: step == .listening ? .white.opacity(0.18) : nil, interactive: step != .listening, in: Capsule())
            .contentShape(Capsule())
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { v in
                    if !pressing {
                        pressing = true
                        guard [Step.card, .saved].contains(step) || isMessage(step) else { return }
                        holdStart = Task {
                            try? await Task.sleep(for: .milliseconds(180))
                            guard !Task.isCancelled, pressing, model.startSoulTalk() else { return }
                            step = .listening
                        }
                    }
                    if step == .listening {
                        let s = clamp(v.translation.width / 46, -1, 1)
                        if (abs(s) >= Rig.armed) != (abs(slide) >= Rig.armed) { Haptics.play(.click) }
                        slide = s
                    }
                }
                .onEnded { _ in
                    pressing = false; holdStart?.cancel()
                    guard step == .listening else { return }
                    let cancel = slide <= -Rig.armed
                    slide = 0
                    Task { await finishTalking(cancel: cancel) }
                })
            .disabled(step == .writing || step == .saving)
            .accessibilityLabel("Hold to change \(agent.name)'s soul")
        }
    }

    private func isMessage(_ s: Step) -> Bool { if case .clarify = s { return true }; if case .failed = s { return true }; return false }

    private func finishTalking(cancel: Bool) async {
        step = .writing
        guard let r = await model.endSoulTalk(cancel: cancel, agent: agent.id) else { step = .card; return }
        if let e = r.error { Haptics.play(.failure); step = .failed(e) }
        else if let q = r.clarify { Haptics.play(.notification); step = .clarify(q) }
        else if r.proposal != nil { Haptics.play(.notification); proposal = r; step = .preview }
        else { step = .failed("Couldn't reach your Mac.") }
    }

    private func save() async {
        guard let id = proposal?.proposal else { return }
        step = .saving
        let (c, err) = await hub.saveSoul(agent.id, proposal: id)
        if let c { Haptics.play(.success); card = c; proposal = nil; step = .saved; hub.event("soul saved: \(agent.id)") }
        else { Haptics.play(.failure); proposal = nil; step = .failed(err ?? "Couldn't save it.") }
    }

    private func undo() async {
        step = .saving
        let (c, err) = await hub.undoSoul(agent.id)
        if let c { Haptics.play(.click); card = c; step = .card } else { step = .failed(err ?? "Couldn't undo it.") }
    }
}

/// × · your voice · ✓, as on the main screen: the side your finger slides toward grows, the other fades.
struct TalkBar: View {
    let slide: Double
    let level: () -> Double
    /// A bar of the waveform: taller in the middle, moving with your voice, and a little even in a pause.
    private func bar(_ i: Int, _ t: Double) -> Double {
        let c: Double = 1 - abs(Double(i) - 5) / 5.5
        let wob: Double = 0.5 + 0.5 * sin(t * (7.3 + Double(i) * 0.9) + Double(i) * 1.7)
        let loud: Double = 0.12 + 0.88 * level()
        return 3 + loud * (6 + 15 * c) * (0.55 + 0.45 * wob)
    }
    var body: some View {
        TimelineView(.animation) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate, cancelK = clamp(-slide / Rig.armed, 0, 1), sendK = clamp(slide / Rig.armed, 0, 1)
            HStack(spacing: 10) {
                Image(systemName: "xmark").font(.system(size: 13 + 2 * cancelK, weight: .bold)).foregroundStyle(Pal.white)
                    .frame(width: 30 + 6 * cancelK, height: 30 + 6 * cancelK).background(Color(white: 0.3 + 0.12 * cancelK), in: Circle())
                    .opacity(1 - 0.5 * sendK)
                HStack(spacing: 2.5) {
                    ForEach(0..<11, id: \.self) { i in Capsule().fill(Pal.white).frame(width: 2.6, height: bar(i, t)) }
                }
                .frame(height: 26)
                Image(systemName: "checkmark").font(.system(size: 13 + 2 * sendK, weight: .bold)).foregroundStyle(.black)
                    .frame(width: 30 + 6 * sendK, height: 30 + 6 * sendK).background(Pal.white, in: Circle())
                    .opacity(1 - 0.5 * cancelK)
            }
        }
    }
}

/// One of an agent's settings picked from a list on the watch (its model, its permissions): its runtime's own setting
/// first (Default), then each choice with a line about it, the current one checked. A tap switches it: the agent
/// restarts with it, and its conversation carries on.
struct ChoiceList: View {
    let title: String
    let items: [ModelChoices.Model]?
    let defaultLabel: String?
    let runtime: String
    let footer: String
    @Binding var picked: String?
    let apply: (String?) async -> String?            // nil once it's set, else why not
    @State private var busy: String??
    @State private var error: String?

    var body: some View {
        List {
            if let items {
                Section {
                    row(nil, "Default", about: defaultLabel.map { "\(AgentRuntimes.name(runtime))'s setting: \($0)" })
                    ForEach(items) { m in row(m.id, m.name, about: m.about) }
                } footer: { Text(footer) }
            } else {
                Text(error ?? "Asking your Mac…").foregroundStyle(Pal.gray)
            }
            if let error, items != nil { Text(error).font(.system(size: 12)).foregroundStyle(Pal.amber) }
        }
        .navigationTitle(title)
    }

    private func row(_ id: String?, _ name: String, about: String?) -> some View {
        Button {
            guard busy == nil, id != picked else { return }
            Haptics.play(.click); busy = .some(id); error = nil
            Task {
                if let e = await apply(id) { error = e; Haptics.play(.failure) }
                else { picked = id; Haptics.play(.success) }
                busy = nil
            }
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(name).foregroundStyle(Pal.white)
                    if let about { Text(about).font(.system(size: 12)).foregroundStyle(Pal.gray) }
                }
                Spacer()
                if busy == .some(id) { ProgressView().frame(width: 16, height: 16) }
                else if picked == id { Image(systemName: "checkmark").foregroundStyle(Pal.clay) }
            }
        }
        .disabled(busy != nil)
        .accessibilityAddTraits(picked == id ? .isSelected : [])
    }
}

/// What an agent runs on: Claude Code or Codex, one under the other with the current one checked. A tap switches it:
/// the hub stops the one and starts the other, and each keeps its own thread for when you switch back. One that isn't
/// installed on the Mac is dimmed.
struct AgentRuntimes: View {
    let agent: AgentInfo
    let hub: HubClient
    @Binding var picked: String
    @State private var switching: String?
    @State private var error: String?

    static let all = ["claude", "codex"]
    static func name(_ id: String) -> String { id == "codex" ? "Codex" : "Claude Code" }
#if os(watchOS)
    private static let check = Pal.clay
#else
    private static let check = Color.white
#endif

    var body: some View {
        let installed = hub.state?.runtimes ?? Self.all
        List {
            Section {
                ForEach(Self.all, id: \.self) { id in
                    let can = installed.contains(id)
                    Button { pick(id, can: can) } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(Self.name(id)).foregroundStyle(can ? Pal.white : Pal.gray)
                                if !can { Text("Not installed on your Mac").font(.system(size: 12)).foregroundStyle(Pal.gray) }
                            }
                            Spacer()
                            if switching == id { ProgressView().frame(width: 16, height: 16) }
                            else if picked == id { Image(systemName: "checkmark").foregroundStyle(Self.check) }
                        }
                    }
                    .disabled(switching != nil)
                    .accessibilityAddTraits(picked == id ? .isSelected : [])
                }
            } footer: {
                Text("It stops one and starts the other. Each keeps its own conversation.")
            }
            if let error { Text(error).font(.system(size: 12)).foregroundStyle(Pal.amber) }
        }
        .navigationTitle("Runs on")
    }

    private func pick(_ id: String, can: Bool) {
        guard id != picked, switching == nil else { return }
        guard can else { error = "\(Self.name(id)) isn't installed on your Mac."; Haptics.play(.failure); return }
        Haptics.play(.click); switching = id; error = nil
        Task {
            if let e = await hub.setRuntime(agent.id, runtime: id) { error = e; Haptics.play(.failure) }
            else { picked = id; Haptics.play(.success) }
            switching = nil
        }
    }
}

/// The voices the Mac speaks in (Kokoro's English ones), British first: a tap plays a sample line in that voice and
/// makes it this agent's.
struct AgentVoices: View {
    let agent: AgentInfo
    let hub: HubClient
    @Binding var picked: String?
    @State private var voices: [VoiceInfo]?
    @State private var speaker = Speaker()
    @State private var error: String?
    @State private var playing: String?

#if os(watchOS)
    private static let check = Pal.clay
    private static let small = Font.system(size: 12)
    private static let quiet = Pal.gray
#else
    private static let check = Color.white                       // the iPhone's colours are white and grays
    private static let small = Font.footnote                     // text styles: they follow the text size
    private static let quiet = Ink.quiet
#endif
    /// "Lily, British" from "bf_lily".
    static func label(_ id: String) -> String {
        let name = id.split(separator: "_").last.map { $0.prefix(1).uppercased() + $0.dropFirst() } ?? id
        return "\(name), \(id.hasPrefix("b") ? "British" : "American")"
    }

    var body: some View {
        List {
            if let voices {
                ForEach(["British", "American"], id: \.self) { accent in
                    Section(accent) {
                        ForEach(voices.filter { $0.accent == accent }) { v in
                            voiceRow(v)
                        }
                    }
                    #if os(iOS)
                    .cardRows()                                            // the Model page's rows
                    #endif
                }
            } else {
                Text(error ?? "Asking your Mac…").foregroundStyle(Self.quiet)
                    #if os(iOS)
                    .listRowBackground(Color.clear)
                    #endif
            }
            if let error, voices != nil {
                Text(error).font(Self.small).foregroundStyle(Pal.amber)
                    #if os(iOS)
                    .listRowBackground(Color.clear)
                    #endif
            }
        }
        .navigationTitle("Voice")
        .task { voices = await hub.voices(); if voices == nil { error = "Can't reach your Mac" } }
    }

    private func voiceRow(_ v: VoiceInfo) -> some View {
        Button { pick(v) } label: {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text(v.name)
                        #if os(iOS)
                        .foregroundStyle(.white)                           // not the tint a list gives a button
                        #endif
                    Text("\(v.gender), grade \(v.grade)").font(Self.small).foregroundStyle(Self.quiet)
                }
                Spacer()
                #if os(iOS)
                if playing == v.id { ProgressView().tint(.white) }
                else if picked == v.id { Image(systemName: "checkmark").font(.body.weight(.semibold)).foregroundStyle(Self.check) }
                #else
                if playing == v.id { ProgressView().frame(width: 16, height: 16) }
                else if picked == v.id { Image(systemName: "checkmark").foregroundStyle(Self.check) }
                #endif
            }
        }
    }

    private func pick(_ v: VoiceInfo) {
        Haptics.play(.click); playing = v.id; error = nil
        Task {
            if let e = await hub.setVoice(agent.id, voice: v.id) { error = e; playing = nil; Haptics.play(.failure); return }
            picked = v.id
            if let d = await hub.speech("/v1/voices/\(v.id)/sample") { _ = speaker.play(d) }
            playing = nil
        }
    }
}
