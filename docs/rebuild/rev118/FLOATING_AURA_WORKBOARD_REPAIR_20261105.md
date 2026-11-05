# VAN live aura and adaptive workboard — owner-requested corrective continuation

The owner reaffirmed that distinct aura field arcs were previously rejected, that the tested aura did not feel live, and that the existing overlay workboard needed clearer features, adaptability, interaction and available-space placement. This correction works inside the existing Android assistant. It does not introduce another mascot, alter the Rive artwork, claim physical device acceptance, or waive the original release gates.

## Root causes addressed

The native flame planner still emitted a stroked contour rim, and the procedural character fallback still emitted large broken progress/pulse/dashed status arcs. The workboard material also drew oval specular arcs through its surface. All three routes now avoid those arcs: the aura executors reject retired line/rim operations, fallback exterior status marks are absent, and workboard reflection is a soft filled gradient instead of an ellipse. Critical warning/error/approval glyphs, text status and the companion orb's physical face/rotation remain intact.

The aura now has an independent 3.6-second flow phase integrated from the existing shared monotonic active-time clock. No second rendering loop is added. Flame licks travel along the silhouette rather than only changing length, and the outer reach no longer clamps tips onto a perfect circular boundary. A static/reduced-motion budget freezes the plan even if a caller supplies changing phases. Hidden/screen-off/thermal and actual-obstruction ceilings still apply.

A full-screen background app had also been treated as an obstruction even when VAN's overlay was above it. The existing optional accessibility window-metadata producer now compares actual window layers using the identifier of VAN's own view. No external node tree or text is inspected. Unknown or higher covering-window metadata retains the conservative pause. Public SDK metadata is obtained from VAN's own view, not a hidden View API.

## Existing workboard improvements

Compact/expanded/maximized presentations now share a bounded responsive layout. The character is in an explicit header instead of extending beyond the board through negative offsets. The whole content width is available for controls and results. Overview, Chat, Voice and Trades have visible selected-state feedback; overview feature cards remain linked to the original genuine routes. Conversation drafts, mode/trade selection and original command execution remain owned by the same existing controllers.

Controls have at least48dp touch targets, readable labels, disabled-empty Send, keyboard Send action, scrolling feature/trade tabs and bounded conversation/results content. Header dragging is separate from tapping the character, scrolling the history or invoking a feature. Hide returns to VAN, and Expand/Full/Compact are explicit. Very small IME/split-screen viewports expose a scrollable compact tray instead of drawing content beyond the native window. The tray offers full workspace access and return to VAN; it does not pretend that a tiny area can fit the complete board.

## Space-aware positioning

The pure planner evaluates right/left/below/above the clicked avatar, ranks usable adjacent rectangles by area and proximity, and fits the board inside measured system/cutout insets and the visible keyboard boundary. If no adjacent rectangle can fit the minimum readable board, it uses the remaining bounded viewport with scrollable content. It does not inspect another application's interface to guess importance or cover arbitrary third-party UI elements.

The first opening records the actual resting character position. Expanding/collapsing retains that anchor, and closing restores it. Intentional board dragging is respected until the board closes, but is still clamped to current safe/IME bounds. The native WindowManager size and Compose layout receive the same allocation. Font scale changes enlarge the desired height within available space; narrow/short surfaces adapt rather than overflow.

## Verification and limits

Source evidence separates genuine Kotlin unit checks, original identity/render tests, shared-source Java2D motion frames, actual native Android source compilation and physical device behavior. The source-render previews execute the shipping Kotlin planner over the original Candidate B fallback bitmap with the same draw operations as Compose; they are NOT S24 screenshots or proof of GPU/battery behavior. Original tests are retained except the obsolete test requiring the specifically rejected stroked rim, which is replaced by exhaustive no-stroke assertions. The old trade-reader source-contract test is updated to verify the actual split lifecycle call chain, rather than a no-longer-existing single-line expression.

The immutable historic aura contract file is unchanged. Its legacy rim constants/types remain for compatibility, but no live planner/executor emits the rejected stroke. This explicit owner correction and the negative tests prevent that stale optional path from silently returning.

The source/publication receipt records exact tests, compiler snapshots and source hashes. Rive production admission, whole APK/signing, physical S24 overlay placement/touch testing, large-font visual review and device frame/power measurements remain separate obligations. No APK or candidate Rive file is installed/promoted by this source repair.
