// WCAG relative luminance for the validated sRGB hex colors used by settings.
export function luminance(hex: string): number {
  const channels = [1, 3, 5].map(index => {
    const value = parseInt(hex.slice(index, index + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722
}
export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (light! + 0.05) / (dark! + 0.05)
}
// Choosing the higher-contrast endpoint always yields at least 4.5:1 for a solid fill.
export function readableText(background: string): string {
  return luminance(background) > 0.179 ? '#000000' : '#ffffff'
}
