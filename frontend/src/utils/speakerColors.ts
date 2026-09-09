/**
 * 说话人颜色分配
 */

const SPEAKER_HUES = [255, 155, 35, 285, 5, 185, 55, 325]

/** 根据说话人 ID 生成头像背景色 */
export function getSpeakerColor(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(60% 0.055 ${hue})`
}

/** 根据说话人 ID 生成浅色背景色 */
export function getSpeakerBg(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(96% 0.02 ${hue})`
}

/** 根据说话人 ID 生成文字色（用于 chip） */
export function getSpeakerTextColor(speakerId: string | number): string {
  const num = typeof speakerId === 'string'
    ? parseInt(speakerId.replace(/\D/g, '').slice(-2)) || 1
    : speakerId
  const hue = SPEAKER_HUES[num % SPEAKER_HUES.length]
  return `oklch(45% 0.08 ${hue})`
}
