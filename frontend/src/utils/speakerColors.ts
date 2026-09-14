/**
 * 说话人颜色分配 / Speaker color assignment
 */

const SPEAKER_HUES = [255, 155, 35, 285, 5, 185, 55, 325]

/** 根据说话人 ID 生成头像背景色 / Generate avatar background color from speaker ID */
export function getSpeakerColor(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(60% 0.055 ${hue})`
}

/** 根据说话人 ID 生成浅色背景色 / Generate light background color from speaker ID */
export function getSpeakerBg(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(96% 0.02 ${hue})`
}

/** 根据说话人 ID 生成文字色（用于 chip） / Generate text color from speaker ID (for chips) */
export function getSpeakerTextColor(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(45% 0.08 ${hue})`
}
