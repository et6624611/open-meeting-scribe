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

/**
 * 说话人**名字**→色相（B5 定稿排版）：名字带数字沿用 ID 数字口径（与个人版「说话人2」同色系），
 * 纯文字名按 FNV-1a 字符哈希确定性散布——同名人跨会议、跨渲染恒同色，不依赖任何服务端配色数据。
 */
export function getSpeakerHueByName(name: string): number {
  const digits = name.replace(/\D/g, '')
  let num: number
  if (digits) {
    num = parseInt(digits.slice(-2)) || 1
  } else {
    let h = 0x811c9dc5
    for (let i = 0; i < name.length; i++) {
      h ^= name.charCodeAt(i)
      h = Math.imul(h, 0x01000193) >>> 0
    }
    num = h >>> 0
  }
  return SPEAKER_HUES[num % SPEAKER_HUES.length]
}

export function getSpeakerNameTextColor(name: string): string {
  return `oklch(45% 0.08 ${getSpeakerHueByName(name)})`
}

export function getSpeakerNameBg(name: string): string {
  return `oklch(96% 0.02 ${getSpeakerHueByName(name)})`
}
