import SwiftUI

extension View {
    /// Older watches use a material background in place of Liquid Glass.
    @ViewBuilder
    func chumsGlass<S: Shape>(tint: Color? = nil, interactive: Bool = false, in shape: S) -> some View {
        if #available(watchOS 26.0, iOS 26.0, *) {
            glassEffect(.regular.tint(tint).interactive(interactive), in: shape)
        } else {
            background(.ultraThinMaterial, in: shape)
                .background((tint ?? .clear), in: shape)
                .overlay(shape.stroke(.white.opacity(0.18), lineWidth: 0.5))
        }
    }
}
