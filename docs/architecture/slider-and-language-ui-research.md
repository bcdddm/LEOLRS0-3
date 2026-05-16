# Slider And Language UI Research

## Purpose

This note turns the current UI direction into an implementation-ready design brief for two related areas:

- small slider / toggle controls across the app
- a compact animated language switch on the top of the app shell

The target visual language is not generic SaaS. It should feel more like:

- paper surface
- stage lighting
- lacquered / metallic accent materials
- pearl-edged jewelry detailing
- compact precision controls
- subtle dotted translucent motion

## Current Project Findings

### 1. Header and shell entry point

The current top shell is rendered in [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:132).

Important nodes:

- page config starts at line 132
- the main title is rendered at line 165
- the app caption sits below it at line 166
- the page shell is rendered at line 174

This means the best place for a homepage-level language switch is near the main title block, not inside the settings page.

### 2. Existing parameter controls are concentrated in the sidebar form

The main density of sliders and toggles lives in [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:185).

Especially important:

- execution and account toggles begin around line 193
- the first core exposure sliders begin at lines 340, 359, and 368
- multiple additional toggles continue through the rest of the sidebar section

This is the right place to define one reusable control style language and apply it consistently.

### 3. Current language control lives in Settings, not in the shell

The existing language selector is a basic selectbox in [trend_system/interfaces/streamlit/pages/settings_page.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/pages/settings_page.py:48).

That is useful as a fallback control, but it is not a refined first-impression switch.

### 4. Default language is currently Chinese

The current default is defined in [config/settings.toml](/Users/leolinum/Documents/LEOLRS0-3/config/settings.toml:6).

Current value:

- `[ui].language = "zh"`

If the desired default becomes English, both the config default and the session preference flow must be updated together.

## Reference Direction

### Jack R. / polished dashboard direction

Relevant traits from Jack R.-style dashboard work:

- compact floating cards instead of flat form rows
- strong section hierarchy with deliberate breathing room
- dark or tinted neutral fields with selective saturated accents
- crisp premium edges with controlled highlights
- a premium “instrument panel” feel rather than generic admin UI

Useful references:

- [Jack R. Dribbble profile](https://dribbble.com/jack-ux-ui-design)
- [XLR Dashboard - Robot Control Interface](https://dribbble.com/shots/27106044-XLR-Dashboard-Robot-Control-Interface)
- [AI Car Inspection SaaS Dashboard](https://dribbble.com/shots/25251171-AI-Car-Inspection-SaaS-Dashboard)
- [PicGen SaaS Image Generator Dashboard](https://dribbble.com/shots/26824576-PicGen-SaaS-Image-Generator-Dashboard)

### Small control references

These are useful not because we should copy them directly, but because they show good tactile behavior for compact controls:

- [Notification Slider - Microinteraction](https://dribbble.com/shots/12215679-Notification-Slider-Microinteraction)
- [On/Off Toggle Switch Animation](https://dribbble.com/shots/26387857-On-Off-Toggle-Switch-Animation)
- [UI - Language Switch](https://dribbble.com/shots/360605-UI-Language-Switch)
- [Neumorphic Dashboard](https://dribbble.com/shots/10728974-Neumorphic-Dashboard)

## Design Thesis For This Project

The app is currently function-first and information-dense. The redesign should not fight that. Instead, it should make the controls feel:

- more deliberate
- more tactile
- more legible at small sizes
- more premium without harming speed

The right direction is:

- paper as the base material
- enamel / lacquer accent surfaces for active states
- pearl-luster edges on important boundaries
- very small but high-precision slider thumbs
- fine border highlights instead of loud shadows
- micro-animations that suggest mechanical motion, not playful toy motion

## Shape Language

### Non-negotiable rule

Avoid rounded rectangles everywhere unless the element is intentionally a pill or capsule control.

That means:

- no standard card with `12px` or `16px` rounded corners
- no default rounded-rect buttons
- no soft SaaS tiles
- no generic rounded input boxes unless they are transformed into another silhouette

### Approved shapes

- pills and capsules for switches, slider rails, and tiny selectors
- clipped panels with chamfered or faceted corners
- shallow arch-top panels
- shield-like metric plates
- hex-cut or octagonal detail frames for small numeric badges
- elongated lozenge shapes for tags and active indicators

### Pearl edge principle

Every important object edge should feel like it has been finished by hand, similar to a jewelry bezel or a polished pearl rim.

This should be expressed through:

- a thin bright inner edge
- a softer warmer outer falloff
- subtle tonal variation across the edge, not a flat stroke
- occasional micro-specular highlights on top-left or top-center edges

Avoid:

- thick white outlines
- plastic-looking bevels
- heavy neumorphic puffiness
- chrome-like mirror reflections

## Material And Color System

### Core palette

Suggested project palette:

- Paper Ivory: `#F4F0E8`
- Warm Paper Shadow: `#E7DFD1`
- Carbon Ink: `#1A1D1F`
- Prussian Blue: `#12395B`
- Deep Prussian Blue: `#0D2A44`
- British Racing Green: `#164A3C`
- Metallic Racing Green Highlight: `#2B6A58`
- Palace Wall Red: `#9E2F2F`
- Aged Gold Accent: `#AE8F54`
- Soft Mist White: `rgba(255,255,255,0.62)`

### Material interpretation for the three hero colors

These are not plain brand colors. Each one needs a distinct material character.

#### 1. Prussian Blue

Material direction:

- mineral
- lapis-lazuli-like
- deep blue with stony depth

Visual rules:

- base should not be flat navy
- add subtle tonal marbling or mineral variation
- top highlight should feel cool and polished, not glossy plastic
- dark pockets can lean slightly toward indigo-black

Suggested support tones:

- Lapis Highlight: `#2C5D86`
- Mineral Midtone: `#1A4468`
- Stone Shadow: `#0B2236`

#### 2. British Racing Green

Material direction:

- metallic
- enamel over metal
- dense reflective green

Visual rules:

- include a controlled metallic light band
- preserve depth in the dark base
- avoid neon or flat emerald behavior
- reflections should be narrow and deliberate

Suggested support tones:

- Metallic Sheen: `#3A7A66`
- Enamel Midtone: `#245847`
- Deep Body: `#102F26`

#### 3. Palace Wall Red

Material direction:

- matte
- ceremonial
- softly weathered mineral-pigment red

Visual rules:

- finish should look satin-matte or finely sanded
- avoid candy gloss
- keep the red grounded and slightly earthy
- highlights should be diffused, not sharp

Suggested support tones:

- Matte Lift: `#B54848`
- Pigment Midtone: `#9E2F2F`
- Burnished Shadow: `#6F2020`

### How each color should behave

- `Paper Ivory` and `Warm Paper Shadow` should dominate backgrounds and panel surfaces.
- `Prussian Blue` should be the most serious, analytical accent. Use it for selected tabs, key active rails, and data-emphasis states.
- `British Racing Green` should feel lacquered and metallic. Use it for “enabled”, “healthy”, “confirmed”, or “active precision mode” states.
- `Palace Wall Red` should be reserved and ceremonial, not danger-only. Use it for strategic emphasis, countdown tension, and selected hero details.
- `Aged Gold Accent` should be sparse. Use it only for tiny separators, edge highlights, or premium detailing.

### Finish rules

- Do not use flat pure green, pure blue, or pure red blocks.
- Every accent color should have at least one darker underside and one soft top highlight.
- Important edges should carry a pearl-like luster rather than a flat border.
- Avoid purple gradients entirely.
- Avoid glassmorphism-heavy blur as the main identity.
- Blue should feel mineral, green should feel metallic, and red should feel matte.

### Edge recipe

Recommended border stack for premium surfaces:

- outer contour: `1px` low-contrast warm shadow
- main rim: `1px` semi-opaque pearl highlight
- optional inner hairline: very faint cool or warm tint depending on the fill

This layered edge treatment should replace the usual rounded-card visual pattern.

## Slider Design System

### Role

Most sliders here are not casual controls. They represent strategy boundaries, risk exposure, and threshold logic. They should look like precision instruments.

### Proposed slider anatomy

- Track height: `6px`
- Visible rail shape: long pill
- Rail base: warm neutral line with subtle inset shadow
- Active fill: left-to-right lacquer gradient
- Thumb size: `14px to 16px`
- Thumb shape: slightly oval pearl-metal bead, not a default circle
- Thumb ring: `1px` highlight border plus soft underside shadow
- Tick marks: only on strategic sliders, and only at meaningful intervals
- Value label: compact capsule above or beside the track for focused sliders

### Visual expression by slider type

1. Exposure sliders

- Use `Prussian Blue` fill
- Add discreet milestone ticks at `0 / 100 / 200 / 300`
- Make the thumb feel dense and mechanical

2. Threshold sliders

- Use `British Racing Green` fill
- Keep them quieter than exposure sliders
- Show value as a small engraved pill

3. Tension / warning sliders

- Use `Palace Wall Red` only when the setting is truly risk-oriented
- Red should not be the default fill state

### Interaction behavior

- Hover: rail highlight brightens slightly, thumb rises by `1px`
- Drag start: thumb scales to `1.05`
- Dragging: add a faint glow trail or value capsule reveal
- Release: tiny eased settle-back motion

Recommended motion character:

- duration around `160ms to 220ms`
- easing should feel “weighted”, not springy-cartoon

### Streamlit-specific implementation note

Because Streamlit widgets are opinionated, the likely path is:

- wrap each slider group inside styled containers
- override widget CSS selectively
- use helper captions and mini labels to create the precision feel around the native control

Do not try to fake every slider entirely from scratch unless Streamlit styling proves insufficient.

## Toggle Design System

### General rule

Toggles should look like miniature lacquered switches, not mobile OS clones.

They are one of the few places where a pill silhouette is explicitly correct.

### Proposed anatomy

- overall width: compact
- track: `28px to 34px`
- knob: `12px to 14px`
- off state: paper-shadow neutral
- on state: metallic green or prussian blue depending on context
- border: thin, crisp, slightly warm
- active top sheen: subtle

### Toggle semantic mapping

- enable / active / allowed: metallic racing green
- display-only / UI-view toggles: prussian blue
- destructive or high-risk mode: palace red only if necessary

## Dotted Semi-Transparent Motion Layer

This is one of the most distinctive opportunities in the redesign.

### Best use cases

- behind the hero language switch
- behind a focused slider while dragging
- in selected top-level cards
- in empty space near the title zone

### Visual recipe

- tiny circular dots, `1px to 3px`
- low opacity, usually `0.08 to 0.24`
- clustered in arcs or drift bands, not uniform grids
- tinted by the active accent color
- some dots slightly blurred, some crisp

### Motion recipe

- slow drift
- occasional parallax offset on hover
- no random explosive particles
- no constant busy sparkle

The goal is “air and atmosphere”, not decoration for its own sake.

## Homepage Language Switch

### Objective

The switch should feel jewel-like, exact, and immediately understandable in both languages.

### Placement

Best location:

- on the same horizontal band as `LEOLRS0-3`
- aligned to the right side of the title row

Do not bury it only in Settings.

### Structure

Recommended form:

- outer shell: tiny horizontal pill
- left label: `EN`
- right label: `中文`
- moving indicator: a lacquer bead / mini shuttle
- default selected side: `EN`

### Motion concept

When toggled:

- the bead slides with a very short weighted motion
- the active label sharpens from `0.72` opacity to full opacity
- inactive label softens slightly
- a faint dotted wake or dust trail appears behind the bead for `150ms to 220ms`

### Visual states

- base shell: paper-tone with engraved border
- pearl rim around the shell and shuttle
- active English: prussian blue bead
- active Chinese: palace wall red bead or racing green bead

Preferred mapping:

- `EN` default: Prussian Blue
- `中文` active: Palace Wall Red

This creates a memorable dual-language personality without becoming flashy.

### Accessibility / usability rules

- label text must remain visible in both states
- the hit area should be larger than the visible switch
- the state should remain understandable with motion disabled
- keyboard focus must receive a clear outline

## Implementation Priorities

### Phase 1: visual foundation

1. Add shared shell CSS variables for:

- paper tones
- three core accents
- edge highlight
- pearl rim highlight
- shadow recipe
- dot opacity

2. Restyle the app shell header and nav first

- [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:165)
- [trend_system/interfaces/streamlit/app_shell.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/app_shell.py:40)

### Phase 2: language switch

1. Add a compact switch beside the main title
2. Make English the default selected language
3. Keep the Settings page language selectbox as the secondary fallback control

Files likely affected:

- [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:148)
- [trend_system/interfaces/streamlit/shared/text.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/interfaces/streamlit/shared/text.py:7)
- [config/settings.toml](/Users/leolinum/Documents/LEOLRS0-3/config/settings.toml:6)

### Phase 3: slider and toggle styling

Start with the most important strategic controls:

- minimum equivalent exposure
- maximum equivalent exposure
- minimum rebalance threshold
- allow leveraged ETF
- composite module enabled
- fixed exposure tiers only

Key file:

- [trend_system/gui.py](/Users/leolinum/Documents/LEOLRS0-3/trend_system/gui.py:340)

### Phase 4: secondary motion layer

Add dotted translucent ambient motion only after the static hierarchy works.

Do not add motion before spacing, color contrast, and component states are correct.

## Recommended Constraints

- Keep motion subtle and short.
- Keep red usage disciplined.
- Avoid decorative gradients on every component.
- Use gold only for detailing.
- Preserve quick scanning for strategy inputs.
- Never make the control look expensive at the cost of clarity.

## Practical Next Step

The best next implementation step is:

1. introduce shell-level CSS variables and surface styles
2. replace the title row with a two-column header
3. add the compact animated `EN / 中文` switch there
4. then restyle the three core exposure sliders as the first premium control set

That sequence gives the redesign a visible identity quickly while keeping risk low.
