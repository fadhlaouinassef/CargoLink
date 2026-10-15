---
name: CargoLink Design System
colors:
  surface: '#f9faf7'
  surface-dim: '#d9dad8'
  surface-bright: '#f9faf7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f1'
  surface-container: '#edeeeb'
  surface-container-high: '#e7e8e6'
  surface-container-highest: '#e2e3e0'
  on-surface: '#191c1b'
  on-surface-variant: '#404943'
  inverse-surface: '#2e312f'
  inverse-on-surface: '#f0f1ee'
  outline: '#707973'
  outline-variant: '#c0c9c2'
  surface-tint: '#326850'
  primary: '#2a6049'
  on-primary: '#ffffff'
  primary-container: '#437960'
  on-primary-container: '#c7ffe1'
  inverse-primary: '#9ad3b5'
  secondary: '#81551d'
  on-secondary: '#ffffff'
  secondary-container: '#ffc481'
  on-secondary-container: '#794f17'
  tertiary: '#3b5d49'
  on-tertiary: '#ffffff'
  tertiary-container: '#537661'
  on-tertiary-container: '#d5fce1'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#b5efd1'
  primary-fixed-dim: '#9ad3b5'
  on-primary-fixed: '#002114'
  on-primary-fixed-variant: '#17503a'
  secondary-fixed: '#ffddb9'
  secondary-fixed-dim: '#f5bc79'
  on-secondary-fixed: '#2b1700'
  on-secondary-fixed-variant: '#653e05'
  tertiary-fixed: '#c5ecd2'
  tertiary-fixed-dim: '#aacfb6'
  on-tertiary-fixed: '#002112'
  on-tertiary-fixed-variant: '#2c4e3b'
  background: '#f9faf7'
  on-background: '#191c1b'
  surface-variant: '#e2e3e0'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 32px
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 30px
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 18px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  margin: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system delivers a reliable, efficient, and approachable professional identity for CargoLink, a freight transportation marketplace in Tunisia. The visual style balances industrial dependability with welcoming clarity, drawing from a Corporate / Modern aesthetic. The interface evokes trust, operational precision, and logistical ease, ensuring seamless navigation for both shippers and transporters.

## Colors

The color palette anchors the platform in professional logistics while offering warm, trustworthy accents. The primary green (#437960) drives core interactive elements and key actions, supported by a deep structural green (#3D5F4B) for high-contrast headers and framing. Golden sand (#DCA565) serves as a warm accent for highlights, statuses, and call-to-actions. The light background (#F7F8F5) provides a clean, breathable canvas, paired with anthracite text (#2F3335) to ensure optimal legibility and reduced eye strain during prolonged use.

## Typography

Typography pairs the welcoming, geometric precision of Plus Jakarta Sans for headings with the neutral, highly legible Inter for body text and labels. This combination ensures clear hierarchy across complex dashboard data, shipment listings, and freight details. Ensure text scaling strictly adheres to accessibility guidelines, substituting mobile-specific headline sizes on viewports under 768px.

## Layout & Spacing

A responsive 12-column fluid grid system organizes dense logistical data, listings, and tracking dashboards. Outer margins scale down from 2rem on desktop to 1rem on mobile devices, maintaining consistent safety boundaries. The spacing rhythm relies on a reliable 4px/8px base unit, ensuring comfortable breathing room between shipment cards, status badges, and interactive controls without wasting valuable screen estate.

## Elevation & Depth

Visual hierarchy relies on subtle ambient shadows and tonal layering to separate interactive cards from the light background. Containers use soft, low-opacity shadows (e.g., `0px 4px 12px rgba(47, 51, 53, 0.06)`) to give shipment cards and modal dialogs a tactile, lifted feel without appearing heavy or distracting. Hover states subtly increase shadow diffusion to provide immediate tactile feedback.

## Shapes

The shape language employs soft, approachable geometry. Cards, inputs, and buttons feature slightly rounded corners (0.25rem base, scaling to 0.5rem for larger containers) to soften the industrial nature of freight management, creating an inviting, modern user experience.

## Components

- **Buttons:** Primary actions utilize the deep primary green (#437960) with anthracite text or white contrast depending on state, featuring soft rounded corners and subtle hover elevation. Secondary buttons use ghost or outlined styles with anthracite borders.
- **Chips & Badges:** Used extensively for shipment statuses (e.g., "In Transit", "Delivered", "Pending"). Backgrounds use tinted versions of the primary or golden sand colors for instant legibility.
- **Lists:** Structured with clear dividing lines in neutral tones, optimized for scanning origin, destination, weight, and vehicle type.
- **Checkboxes & Radio Buttons:** Styled with the primary green accent to maintain clean form interactions when filtering searches.
- **Input Fields:** Built with crisp anthracite borders, light background fills, and clear placeholder text in muted gray. Focus states engage the primary green ring.
- **Cards:** Shipment and transporter cards feature slightly rounded corners, light background containers (#FFFFFF against the #F7F8F5 canvas), and discrete ambient shadows.
- **Additional Components:** Implement data tables for freight tracking, step-based wizards for shipment creation, and interactive map containers with custom route overlays.