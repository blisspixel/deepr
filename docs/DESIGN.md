# Deepr Design System

## Design Philosophy

Deepr is a research automation platform for professionals. The design should feel:
- **Clean & Minimal**: Focus on content, not chrome
- **Modern & Refined**: Contemporary aesthetics without being trendy
- **Conversational**: Natural interaction, not form-filling
- **Professional**: Trustworthy for serious work

## Color Palette

### Light Mode
- **Background**: `#FAFAFA` (soft off-white, reduces eye strain)
- **Surface**: `#FFFFFF` (pure white for cards/panels)
- **Text Primary**: `#1A1A1A` (near-black, softer than pure black)
- **Text Secondary**: `#6B7280` (medium gray for labels/captions)
- **Border**: `#E5E7EB` (light gray, subtle separation)

### Dark Mode
- **Background**: `#0A0A0A` (very dark gray, not pure black)
- **Surface**: `#151515` (slightly lighter for elevation)
- **Text Primary**: `#F5F5F5` (off-white, prevents blooming)
- **Text Secondary**: `#9CA3AF` (lighter gray for secondary text)
- **Border**: `#262626` (subtle borders in dark mode)

### Accent Colors
- **Primary**: `#2563EB` (blue for primary actions, links)
- **Success**: `#10B981` (green for completed, success states)
- **Warning**: `#F59E0B` (amber for pending, warnings)
- **Error**: `#EF4444` (red for errors, destructive actions)
- **Info**: `#8B5CF6` (purple for info, secondary highlights)

## Typography

### Font Families

```css
/* Interface Font - System Native for OS integration */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto",
             "Helvetica Neue", Arial, sans-serif;

/* Code/Monospace - For code blocks and technical content */
font-family: "JetBrains Mono", "IBM Plex Mono", "Source Code Pro",
             Consolas, "Courier New", monospace;
```

### Type Scale

- **Display**: 3rem (48px) - Page titles, hero text
- **H1**: 2.25rem (36px) - Main section headings
- **H2**: 1.875rem (30px) - Subsection headings
- **H3**: 1.5rem (24px) - Card titles
- **Body**: 1rem (16px) - Primary body text
- **Small**: 0.875rem (14px) - Labels, captions
- **Tiny**: 0.75rem (12px) - Micro-copy, timestamps

### Font Weights

- **Regular**: 400 - Body text
- **Medium**: 500 - Emphasized text, labels
- **Semibold**: 600 - Subheadings, buttons
- **Bold**: 700 - Headings, important text

## Spacing System

Use 4px base unit with consistent scale:

```
1 = 4px
2 = 8px
3 = 12px
4 = 16px
5 = 20px
6 = 24px
8 = 32px
10 = 40px
12 = 48px
16 = 64px
20 = 80px
```

## Components

### Cards
- Background: Surface color
- Border: 1px solid border color
- Radius: 12px (modern, not too rounded)
- Shadow: Subtle, only on hover/focus
- Padding: 24px (6 units)

### Buttons

**Primary**
- Background: Primary color
- Text: White
- Padding: 12px 24px
- Radius: 8px
- Hover: Darken 10%

**Secondary**
- Background: Transparent
- Border: 1px solid border
- Text: Text primary
- Hover: Light background

**Ghost**
- Background: Transparent
- Text: Text secondary
- Hover: Light background

### Inputs
- Background: Surface
- Border: 1px solid border color
- Radius: 8px
- Padding: 12px 16px
- Focus: 2px ring in primary color
- Placeholder: Text secondary

### Status Badges
- **Processing**: Blue background, blue text
- **Completed**: Green background, green text
- **Failed**: Red background, red text
- **Queued**: Gray background, gray text

## Layout

### Container Widths
- **Narrow**: 640px (forms, focused content)
- **Standard**: 896px (default max-width)
- **Wide**: 1280px (dashboards, tables)
- **Full**: 100% (special cases)

### Grid System
- 12-column responsive grid
- Gutter: 24px (6 units)
- Breakpoints:
  - Mobile: 0-639px
  - Tablet: 640-1023px
  - Desktop: 1024px+

## Interaction States

### Hover
- Buttons: Background darkens/lightens 10%
- Cards: Subtle shadow appears
- Links: Underline appears
- Transition: 150ms ease-in-out

### Focus
- 2px ring in primary color
- Offset: 2px
- Never remove focus indicators

### Active
- Scale: 98% (subtle press effect)
- Transition: 100ms

### Disabled
- Opacity: 0.5
- Cursor: not-allowed
- No hover effects

## Iconography

- Use simple, line-based icons
- 24px default size
- 1.5px stroke width
- Match text color (inherit)

## Content Formatting

### Code Blocks
- Background: Darker/lighter than surface
- Border: 1px solid border
- Radius: 8px
- Padding: 16px
- Font: Monospace
- Copy button: Top-right corner

### Lists
- Bullet: Simple disc or dash
- Spacing: 8px between items
- Indent: 24px for nested

### Tables
- Header: Semibold, border-bottom
- Rows: Alternate subtle background
- Padding: 12px 16px
- Hover: Highlight row

## Animation Principles

- **Subtle**: Never distracting
- **Fast**: 150ms for micro-interactions
- **Purposeful**: Only when providing feedback
- **Reduced Motion**: Respect prefers-reduced-motion

## Accessibility

- **Contrast**: WCAG AA minimum (4.5:1 for text)
- **Focus**: Always visible focus indicators
- **Keyboard**: Full keyboard navigation
- **Screen Readers**: Semantic HTML, ARIA labels
- **Touch**: Minimum 44px touch targets

## Voice & Tone

- **Clear**: Direct, no jargon
- **Concise**: Respect user's time
- **Helpful**: Guide, don't gatekeep
- **Professional**: Serious but not stuffy
- **Human**: Conversational, not robotic
