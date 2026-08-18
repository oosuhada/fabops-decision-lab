# AI × UI/UX Visual Reference Catalog

> Working reference for `signal-garden`, `scenario-prism`, `generative-decision-surface`, and `ai-memory-museum`.
>
> 조사 기준일: 2026-08-23

이 문서는 네 프로젝트의 시각적 완성도를 높이기 위한 구현 참고 자료다. 단순히 링크를 구경하는 용도가 아니라, 각 저장소의 담당 개발자가 후보를 검토하고 실제 인터랙션이나 시각 시스템에 적용하기 위한 작업 지침으로 사용한다.

## Usage Rules / 사용 규칙

1. 프로젝트 작업을 시작하기 전에 이 문서를 끝까지 읽는다.
2. 각 후보의 README, Demo, LICENSE를 다시 확인한다.
3. 라이선스가 허용하는 경우에만 코드를 복사하거나 수정한다.
4. 라이선스가 없거나 불명확하면 코드 대신 시각 원리와 인터랙션만 참고한다.
5. 유료 Framer Marketplace 컴포넌트의 코드는 복사하지 않는다.
6. 가져온 코드와 강하게 참고한 구현은 프로젝트의 `CREDITS.md`에 기록한다.
7. 원본 라이선스나 저작권 고지를 보존해야 하는 경우 반드시 보존한다.
8. 라이브러리를 설치만 하고 사용하지 않는다. 실제 핵심 인터랙션에 사용한 경우만 의존성으로 남긴다.
9. 시각 효과는 제품 상태, 정보 관계, 신뢰도, 불확실성 또는 탐색 구조를 전달해야 한다.
10. 동일한 컴포넌트나 시각 효과를 네 프로젝트에 반복 적용하지 않는다.

## License Legend / 라이선스 구분

- **GREEN**: MIT, Apache-2.0, BSD, ISC 등 비교적 차용하기 쉬운 라이선스. 그래도 LICENSE와 고지 조건을 확인한다.
- **YELLOW**: MPL, Commons Clause, PolyForm, custom license 등 조건부 사용. 조건을 검토한 후 사용한다.
- **RED**: 라이선스 미탐지 또는 production 제약. 코드 복사보다 시각 레퍼런스로만 사용한다.

`git clone`할 수 있다는 사실은 코드를 다른 제품에 편입할 권리를 의미하지 않는다.

## Highest-Priority References / 최우선 후보

| Reference | Demo | License | Best fit | What to borrow |
|---|---|---:|---|---|
| [Canvas UI](https://github.com/DavidHDev/canvas-ui) | [canvasui.dev](https://canvasui.dev/) | YELLOW: MIT + Commons Clause | Scenario Prism, Memory Museum | live DOM 위 Glass, Shatter, VHS, Liquid, Particle Reveal |
| [Paper Shaders](https://github.com/paper-design/shaders) | [shaders.paper.design](https://shaders.paper.design/) | GREEN: Apache-2.0 | Scenario Prism, Memory Museum | zero-dependency canvas shader와 material vocabulary |
| [Liquid Glass Studio](https://github.com/iyinchao/liquid-glass-studio) | [Demo](https://liquid-glass-studio.vercel.app/) | GREEN: MIT | Scenario Prism | WebGL2/WebGPU refraction, 설정 패널, material tuning |
| [ShaderGradient](https://github.com/ruucm/shadergradient) | [shadergradient.co](https://shadergradient.co/) | RED: no license detected | Scenario Prism | Framer형 3D gradient hero와 색·카메라 구성 |
| [React Three Fiber](https://github.com/pmndrs/react-three-fiber) | [Examples](https://pmndrs.github.io/examples/) | GREEN: MIT | Scenario Prism, Memory Museum | 3D scene, interaction, monitor, fisheye, glass cards |
| [React Bits](https://github.com/DavidHDev/react-bits) | [reactbits.dev](https://reactbits.dev/) | YELLOW: MIT + Commons Clause | Selective use only | Splash Cursor, Liquid Chrome, Threads, Dither, Pixel Transition |
| [Open Generative UI](https://github.com/CopilotKit/OpenGenerativeUI) | [Demo](https://opengenerativeui.copilotkit.ai/) | GREEN: MIT | Generative Decision Surface | AI-generated live HTML, SVG, 3D and simulations |
| [genui-canvas](https://github.com/LuisErlacher/genui-canvas) | README visual proof | GREEN: MIT | Generative Decision Surface | infinite canvas와 양방향 agent/component state |
| [Onlook](https://github.com/onlook-dev/onlook) | [onlook.com](https://onlook.com/) | GREEN: Apache-2.0 | Generative Decision Surface | AI-first visual editor, property panel, preview workflow |
| [Graphite](https://github.com/GraphiteEditor/Graphite) | [graphite.art](https://graphite.art/) | GREEN: Apache-2.0 | Signal Garden, Decision Surface | procedural node UI와 전문 편집기 정보 구조 |
| [Bruno Simon Folio](https://github.com/brunosimon/folio-2019) | [bruno-simon.com](https://bruno-simon.com/) | GREEN: MIT | AI Memory Museum | 웹페이지 대신 이동 가능한 3D 세계를 사용하는 방식 |
| [r3f-scroll-rig](https://github.com/14islands/r3f-scroll-rig) | README demos | GREEN: MIT | AI Memory Museum | DOM과 WebGL의 scroll-position 동기화 |
| [Theatre.js](https://github.com/theatre-js/theatre) | [theatrejs.com](https://www.theatrejs.com/) | GREEN: Apache-2.0 | Scenario Prism, Memory Museum | 카메라·조명·오브젝트의 cinematic timeline |
| [liquid-glass-react](https://github.com/rdev/liquid-glass-react) | README demos | GREEN: MIT | Scenario Prism | refraction, frost, aberration, elasticity |
| [HTML in Canvas](https://github.com/en-dash-consulting/html-in-canvas-dot-dev) | [Demo gallery](https://html-in-canvas.dev/demos/) | GREEN: MIT | Experimental enhancement | 3D room, CSS-to-shader, liquid glass, page curl |

## Liquid Glass, Transparency, and Shaders

### Code candidates

- [rdev/liquid-glass-react](https://github.com/rdev/liquid-glass-react) — GREEN MIT — React glass surface.
- [shuding/liquid-glass](https://github.com/shuding/liquid-glass) — GREEN MIT — copy-paste SVG displacement shader.
- [iyinchao/liquid-glass-studio](https://github.com/iyinchao/liquid-glass-studio) · [Demo](https://liquid-glass-studio.vercel.app/) — GREEN MIT — WebGL2/WebGPU glass.
- [liquefy-ui/liquefy-ui](https://github.com/liquefy-ui/liquefy-ui) · [Demo](https://liquefy-ui.com/) — GREEN MIT — refraction, accessible primitives, jelly springs.
- [samasante/liquid-glass](https://github.com/samasante/liquid-glass) — GREEN MIT — headless React lens over live DOM.
- [dashersw/liquid-glass-js](https://github.com/dashersw/liquid-glass-js) — GREEN MIT — Apple-inspired web glass library.
- [PallavAg/liquid-glass-web-react](https://github.com/PallavAg/liquid-glass-web-react) · [Demo](https://agpallav.com/liquid-glass) — GREEN MIT — cross-browser SVG displacement.
- [ybouane/liquidglass](https://github.com/ybouane/liquidglass) · [Demo](https://liquid-glass.ybouane.com/) — GREEN per README — WebGL refraction, blur, chromatic aberration.
- [Yousuf-developer/liquid-glass-carousel](https://github.com/Yousuf-developer/liquid-glass-carousel) · [Demo](https://yousuf-portfolio-carousel.vercel.app/) — GREEN MIT — GSAP carousel with liquid lens.
- [paper-design/shaders](https://github.com/paper-design/shaders) · [Demo](https://shaders.paper.design/) — GREEN Apache-2.0 — metaballs, smoke, water, gradients.
- [mattrothenberg/fold-gradient](https://github.com/mattrothenberg/fold-gradient) — GREEN MIT — folded sheets of light.

### Reference-first candidates

- [DavidHDev/canvas-ui](https://github.com/DavidHDev/canvas-ui) · [Demo](https://canvasui.dev/) — YELLOW Commons Clause.
- [DavidHDev/react-bits](https://github.com/DavidHDev/react-bits) · [Demo](https://reactbits.dev/) — YELLOW Commons Clause.
- [naughtyduk/liquidGL](https://github.com/naughtyduk/liquidGL) · [Demo](https://liquidgl.naughtyduk.com/) — YELLOW; README usage terms must be checked.
- [paper-design/liquid-logo](https://github.com/paper-design/liquid-logo) · [Demo](https://liquid.paper.design/) — YELLOW PolyForm Shield.
- [AndrewPrifer/liquid-dom](https://github.com/AndrewPrifer/liquid-dom) · [Demo](https://liquid-dom-showcase.vercel.app/) — RED no license detected.
- [huozhi/vaso](https://github.com/huozhi/vaso) · [Demo](https://vaso-react.vercel.app/) — RED no license detected.
- [archisvaze/liquid-glass](https://github.com/archisvaze/liquid-glass) · [Demo](https://liquid-glass-eta.vercel.app/) — RED no license detected.
- [chiuhans111/fluidglass](https://github.com/chiuhans111/fluidglass) · [Demo](https://chiuhans111.github.io/fluidglass/) — RED reference first.
- [Muggleee/liquid-glass](https://github.com/Muggleee/liquid-glass) · [Demo](https://liquid-glass.liziyang.design/) — RED no license detected.
- [ruucm/shadergradient](https://github.com/ruucm/shadergradient) · [Demo](https://shadergradient.co/) — RED no license detected.

## 3D, Spatial UI, and Cinematic Motion

- [pmndrs/react-three-fiber](https://github.com/pmndrs/react-three-fiber) · [Examples](https://pmndrs.github.io/examples/) — GREEN MIT.
- [pmndrs/drei](https://github.com/pmndrs/drei) · [Docs](https://docs.pmnd.rs/drei) — GREEN MIT — Environment, Float, MeshTransmissionMaterial, Sparkles, Trail, Cloud, CameraControls.
- [pmndrs/react-postprocessing](https://github.com/pmndrs/react-postprocessing) · [Docs](https://docs.pmnd.rs/react-postprocessing) — GREEN MIT — bloom, depth of field, noise, chromatic aberration.
- [pmndrs/uikit](https://github.com/pmndrs/uikit) · [Demo](https://pmndrs.github.io/uikit/docs/) — GREEN MIT — 3D 공간 속 UI.
- [pmndrs/lamina](https://github.com/pmndrs/lamina) — GREEN MIT — layered shader materials.
- [pmndrs/react-three-next](https://github.com/pmndrs/react-three-next) · [Demo](https://react-three-next.vercel.app/) — GREEN MIT — Next.js/R3F starter.
- [pmndrs/gltfjsx](https://github.com/pmndrs/gltfjsx) · [Demo](https://gltf.pmnd.rs/) — GREEN MIT — GLTF to JSX.
- [pmndrs/react-three-rapier](https://github.com/pmndrs/react-three-rapier) · [Demo](https://react-three-rapier.pmnd.rs/) — GREEN MIT — physics.
- [pmndrs/react-three-a11y](https://github.com/pmndrs/react-three-a11y) · [Docs](https://docs.pmnd.rs/a11y/introduction) — verify license — 3D keyboard and screen-reader support.
- [14islands/r3f-scroll-rig](https://github.com/14islands/r3f-scroll-rig) — GREEN MIT — DOM/WebGL sync.
- [theatre-js/theatre](https://github.com/theatre-js/theatre) · [Demo](https://www.theatrejs.com/) — GREEN Apache-2.0.
- [darkroomengineering/lenis](https://github.com/darkroomengineering/lenis) · [Demo](https://lenis.dev/) — GREEN MIT — smooth scroll.
- [darkroomengineering/tempus](https://github.com/darkroomengineering/tempus) — GREEN MIT — shared animation frame loop.
- [motiondivision/motion](https://github.com/motiondivision/motion) · [Demo](https://motion.dev/) — GREEN MIT — gestures and shared layout.
- [lume/lume](https://github.com/lume/lume) · [Demo](https://lume.io/) — GREEN MIT — GPU-powered 3D HTML custom elements.
- [mattdesl/canvas-sketch](https://github.com/mattdesl/canvas-sketch) — GREEN MIT — generative art experiments.
- [vasturiano/3d-force-graph](https://github.com/vasturiano/3d-force-graph) · [Demo](https://vasturiano.github.io/3d-force-graph/example/large-graph/) — GREEN MIT.
- [vasturiano/react-force-graph](https://github.com/vasturiano/react-force-graph) · [Demo](https://vasturiano.github.io/react-force-graph/example/large-graph/) — GREEN MIT.
- [vasturiano/three-globe](https://github.com/vasturiano/three-globe) · [Demo](https://vasturiano.github.io/three-globe/example/links/) — GREEN MIT.
- [isoteriksoftware/react-gallery-3d](https://github.com/isoteriksoftware/react-gallery-3d) · [Demo](https://react-gallery-3d-demo-next.vercel.app/) — GREEN MIT.
- [shehzadres/Webgl-Data-Globe](https://github.com/shehzadres/Webgl-Data-Globe) · [Demo](https://webgl-data-globe.vercel.app/) — GREEN MIT — cinematic camera and atmosphere shader.
- [brunosimon/folio-2019](https://github.com/brunosimon/folio-2019) · [Site](https://bruno-simon.com/) — GREEN MIT.
- [ShAuRyA-Noodle/ThreeJS-Celestial-Forge](https://github.com/ShAuRyA-Noodle/ThreeJS-Celestial-Forge) · [Demo](https://three-js-celestial-forge.vercel.app/) — RED no license detected.
- [abderrahman-png/thevertmenthe-gallery](https://github.com/abderrahman-png/thevertmenthe-gallery) — RED no license detected; visual reference only.

## Infinite Canvas, Graph, and Evidence Maps

- [xyflow/xyflow](https://github.com/xyflow/xyflow) · [Demo](https://xyflow.com/) — GREEN MIT.
- [excalidraw/excalidraw](https://github.com/excalidraw/excalidraw) · [Demo](https://excalidraw.com/) — GREEN MIT.
- [rough-stuff/rough](https://github.com/rough-stuff/rough) · [Demo](https://roughjs.com/) — GREEN MIT.
- [d3/d3](https://github.com/d3/d3) · [Demo gallery](https://d3js.org/) — GREEN ISC.
- [cytoscape/cytoscape.js](https://github.com/cytoscape/cytoscape.js) · [Demo](https://js.cytoscape.org/) — GREEN MIT.
- [antvis/G6](https://github.com/antvis/G6) · [Demo](https://g6.antv.antgroup.com/) — GREEN MIT.
- [projectstorm/react-diagrams](https://github.com/projectstorm/react-diagrams) · [Demo](https://projectstorm.cloud/react-diagrams) — GREEN MIT.
- [reaviz/reaflow](https://github.com/reaviz/reaflow) · [Demo](https://reaflow.dev/) — GREEN Apache-2.0.
- [jacomyal/sigma.js](https://github.com/jacomyal/sigma.js) · [Demo](https://www.sigmajs.org/) — GREEN MIT.
- [kieler/elkjs](https://github.com/kieler/elkjs) — YELLOW; ELK license conditions must be checked.
- [toeverything/blocksuite](https://github.com/toeverything/blocksuite) · [Demo](https://blocksuite.io/) — YELLOW MPL-2.0.
- [GraphiteEditor/Graphite](https://github.com/GraphiteEditor/Graphite) · [Demo](https://graphite.art/) — GREEN Apache-2.0.
- [tldraw/tldraw](https://github.com/tldraw/tldraw) · [Demo](https://tldraw.dev/) — RED for production: default license permits development environments but production requires a separate license.

## Generative UI and AI Editors

- [CopilotKit/OpenGenerativeUI](https://github.com/CopilotKit/OpenGenerativeUI) · [Demo](https://opengenerativeui.copilotkit.ai/) — GREEN MIT.
- [LuisErlacher/genui-canvas](https://github.com/LuisErlacher/genui-canvas) — GREEN MIT.
- [langchain-ai/open-canvas](https://github.com/langchain-ai/open-canvas) · [Demo](https://opencanvas.langchain.com/) — GREEN MIT.
- [wandb/openui](https://github.com/wandb/openui) — GREEN Apache-2.0; README visuals available, public demo may be unavailable.
- [Nutlope/llamacoder](https://github.com/Nutlope/llamacoder) · [Demo](https://www.llamacoder.io/) — GREEN MIT.
- [abi/screenshot-to-code](https://github.com/abi/screenshot-to-code) · [Demo](https://screenshottocode.com/) — GREEN MIT.
- [onlook-dev/onlook](https://github.com/onlook-dev/onlook) · [Demo](https://onlook.com/) — GREEN Apache-2.0.
- [puckeditor/puck](https://github.com/puckeditor/puck) · [Demo](https://puckeditor.com/) — GREEN MIT.
- [prevwong/craft.js](https://github.com/prevwong/craft.js) · [Demo](https://craft.js.org/) — GREEN MIT.
- [plasmicapp/plasmic](https://github.com/plasmicapp/plasmic) · [Demo](https://www.plasmic.app/) — GREEN MIT.
- [GrapesJS/grapesjs](https://github.com/GrapesJS/grapesjs) · [Demo](https://grapesjs.com/) — verify BSD terms.
- [penpot/penpot](https://github.com/penpot/penpot) · [Demo](https://penpot.app/) — YELLOW MPL-2.0.
- [webstudio-is/webstudio](https://github.com/webstudio-is/webstudio) · [Demo](https://webstudio.is/) — RED AGPL-3.0 unless project license is compatible.

## Animated UI and Framer-like Components

- [magicuidesign/magicui](https://github.com/magicuidesign/magicui) · [Demo](https://magicui.design/) — GREEN MIT.
- [ibelick/motion-primitives](https://github.com/ibelick/motion-primitives) · [Demo](https://motion-primitives.com/) — GREEN MIT.
- [kokonut-labs/kokonutui](https://github.com/kokonut-labs/kokonutui) · [Demo](https://kokonutui.com/) — GREEN MIT.
- [ui-layouts/uilayouts](https://github.com/ui-layouts/uilayouts) · [Demo](https://www.ui-layouts.com/) — GREEN MIT.
- [damien-schneider/cuicui](https://github.com/damien-schneider/cuicui) · [Demo](https://cuicui.day/) — GREEN MIT.
- [ColorlibHQ/velora-ui](https://github.com/ColorlibHQ/velora-ui) · [Demo](https://velora.colorlib.com/) — GREEN MIT.
- [imskyleen/animate-ui](https://github.com/imskyleen/animate-ui) · [Demo](https://animate-ui.com/) — RED no license detected.
- [Joangeldelarosa/pxlkit](https://github.com/Joangeldelarosa/pxlkit) · [Demo](https://pxlkit.xyz/) — verify license.

## Project Integration Matrix / 프로젝트별 적용 계획

### 1. Signal Garden

**Target identity:** editorial research tool, botanical intelligence, field notes, evidence cartography.

Preferred combination:

1. `xyflow` for editable spatial structure.
2. `D3 force` for organic evidence clustering.
3. `Rough.js` for ink, annotation, and hand-drawn boundaries.
4. `Graphite` and `Excalidraw` for professional canvas/editor UX references.
5. `Motion` for cards becoming seeds, roots, and clusters.

Avoid:

- Liquid glass as the dominant surface.
- Dark cinematic backgrounds.
- Generic glass cards.
- A central 3D orb.
- Chat-first layout.

Minimum reference adoption goal:

- Use at least two GREEN code candidates.
- Adopt at least three clearly documented interaction or visual principles.

### 2. Scenario Prism

**Target identity:** cinematic executive simulation, dark optics, industrial precision.

Preferred combination:

1. `React Three Fiber` and `Drei` for the central decision object.
2. `Paper Shaders` or `Liquid Glass Studio` for the optical material.
3. `react-postprocessing` for bloom, depth, noise, and aberration.
4. `Theatre.js` for camera and lighting choreography.
5. `Lamina` for layered materials when useful.

Avoid:

- Card grids.
- Infinite canvas.
- Paper textures.
- Multiple unrelated 3D ornaments.
- Copying ShaderGradient code without a clear license.

Minimum reference adoption goal:

- Use at least three GREEN libraries in the real scene.
- The material must encode uncertainty or evidence, not only decoration.

### 3. Generative Decision Surface

**Target identity:** spatial operating system, modular instruments, live computation.

Preferred combination:

1. `OpenGenerativeUI` for streamed live UI concepts.
2. `genui-canvas` for agent/canvas bidirectional state patterns.
3. `Puck` or `Craft.js` for editable component composition.
4. `Onlook` for visual editor information architecture.
5. `Graphite` for ports, nodes, procedural connections.
6. `Motion Primitives` for precise layout reconfiguration.

Avoid:

- A normal chatbot with a preview panel.
- Liquid glass as the main identity.
- Decorative 3D hero objects.
- Static dashboard cards.

Minimum reference adoption goal:

- Use at least two GREEN codebases or libraries.
- Implement visible plan → assemble → connect → recompute states.

### 4. AI Memory Museum

**Target identity:** dreamlike spatial archive, atmospheric exhibition, cinematic memory.

Preferred combination:

1. `react-gallery-3d` for rapid gallery scaffolding.
2. `React Three Fiber`, `Drei`, and `gltfjsx` for the scene.
3. `Bruno Simon Folio` for spatial navigation principles.
4. `r3f-scroll-rig` for optional DOM/WebGL transitions.
5. `Theatre.js` for curator-led camera movement.
6. `react-postprocessing` for atmosphere and depth.
7. `Canvas UI` or HTML-in-Canvas page-curl effects only when licensing/browser support is acceptable.

Avoid:

- Dashboard layout.
- Fixed sidebar as the primary navigation.
- Scenario Prism-style HUD.
- A node graph presented as a museum.

Minimum reference adoption goal:

- Use at least three GREEN 3D libraries or code candidates.
- Provide a deliberate 2D fallback and reduced-motion mode.

## Mandatory Adoption Report Template

각 저장소에 `docs/reference-adoption.md`를 만들고 아래 양식을 채운다.

```md
# Reference Adoption

## Adopted in Code

| Reference | License | Files/feature used | Changes made | Credit location |
|---|---|---|---|---|

## Visual Principles Adopted

| Reference | Observed principle | Our interpretation | Where visible |
|---|---|---|---|

## Investigated but Rejected

| Reference | Reason rejected |
|---|---|

## License Verification

- [ ] LICENSE opened and read
- [ ] Attribution requirements preserved
- [ ] No unknown-license code copied
- [ ] No incompatible copyleft dependency introduced
- [ ] CREDITS.md updated
```

## Acceptance Criteria

각 프로젝트는 다음을 만족해야 한다.

- 이 문서에서 최소 10개 후보를 실제로 조사한다.
- 그중 최소 3개를 prototype하거나 비교한다.
- 최소 2개 이상의 허용된 외부 구현을 실제 핵심 경험에 적용한다.
- 사용하지 않은 후보를 무작정 dependency에 남기지 않는다.
- 프로젝트별 `CREDITS.md`와 `docs/reference-adoption.md`를 작성한다.
- 네 프로젝트가 같은 component library demo처럼 보이지 않아야 한다.
- 1440px desktop과 390px mobile에서 검증한다.
- low-power mode, reduced motion, WebGL fallback을 검증한다.
- README에 최신 screenshot 또는 GIF를 추가한다.
- 공개 배포 전에 모든 라이선스를 다시 확인한다.

