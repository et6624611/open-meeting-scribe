/**
 * §7 锁定文案块（QA B5 断言基准） / Locked privacy copy (QA B5 assertion baseline)
 *
 * 来源：shared/P0-UIUX-SPEC-20261029.md v1.0 §7，产品经理定稿。
 * 三处 UI 表面必须逐字一致（登录页隐私说明 / Settings「数据位置」三行表 / 上传知情同意卡正文），
 * 任一字符差异判 P0 FAIL。所有表面一律 import 本常量，禁止手抄。
 * Source: UI spec §7. All three surfaces MUST render exactly these lines — import, never hand-copy.
 */
export const LOCKED_PRIVACY_LINES: readonly string[] = [
  '你的会议录音和音频只保存在这台电脑上，不会离开本机。',
  '会议定稿后的文字内容（转写文本、纪要、决策流、笔记、术语）会保存到公司服务器，方便你在任何设备上查看。',
  '你的声纹信息和 API 密钥永远不上传。',
] as const
