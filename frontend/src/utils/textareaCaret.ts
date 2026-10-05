/**
 * textarea 光标像素坐标测量 / textarea caret pixel coordinates
 *
 * 镜像 div 技术：复制 textarea 的排版相关 computed 样式，填入光标前文本 + 探针 span，
 * 读取 span 相对镜像左上角的偏移，减去 textarea 的 scrollTop/scrollLeft，返回相对
 * textarea 边框盒（border-box）左上角的 { left, top }（CSS 像素，含 textarea 自身内边距）。
 * 调用方再叠加 textarea 相对定位祖先的偏移即可得到菜单落位坐标。CJK 自动换行场景可靠。
 */

// 需要从 textarea 复制到镜像 div 的样式属性（影响文本流布局）
const COPY_PROPS: string[] = [
  'fontFamily', 'fontSize', 'fontWeight', 'fontWeight', 'fontStyle', 'fontVariant',
  'lineHeight', 'letterSpacing', 'wordSpacing', 'textTransform', 'textIndent',
  'whiteSpace', 'wordBreak', 'overflowWrap', 'tabSize',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'boxSizing', 'direction',
]

export function getCaretCoordinates(el: HTMLTextAreaElement, position: number): { left: number; top: number } {
  const style = window.getComputedStyle(el)
  const div = document.createElement('div')

  // 镜像必须不可见但参与布局（display 不能为 none，否则无法测量）
  div.style.position = 'absolute'
  div.style.top = '-9999px'
  div.style.left = '0'
  div.style.visibility = 'hidden'
  div.style.overflow = 'hidden'
  // 镜像与 textarea 同宽，文字换行才一致
  div.style.width = `${el.clientWidth}px`
  div.style.minHeight = '0'
  div.style.maxHeight = 'none'
  div.style.flex = 'none'

  const src = style as unknown as Record<string, string>
  const dst = div.style as unknown as Record<string, string>
  for (const p of COPY_PROPS) {
    if (src[p] !== undefined) dst[p] = src[p]
  }
  // 镜像必须把文本按原样换行（textarea 用 pre-wrap）
  div.style.whiteSpace = 'pre-wrap'
  div.style.overflowWrap = 'break-word'

  const text = el.value.slice(0, position)
  div.textContent = text
  const span = document.createElement('span')
  // 用零宽占位保证结尾换行/空格也被计入
  span.textContent = el.value.slice(position) || '.'
  div.appendChild(span)

  document.body.appendChild(div)
  const left = span.offsetLeft - el.scrollLeft
  const top = span.offsetTop - el.scrollTop
  document.body.removeChild(div)

  return { left, top }
}
