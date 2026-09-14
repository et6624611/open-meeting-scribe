#!/usr/bin/env python3
"""
scripts/gen_i18n_po.py — 从 messages.pot 生成 zh_CN / en 的 .po 文件 / Generate zh_CN / en .po files from messages.pot

工作流 / Workflow:
  1. pybabel extract 已生成 core/i18n/locales/messages.pot（英文 msgid） / pybabel extract generated core/i18n/locales/messages.pot (English msgid)
  2. 本脚本读取 .pot 的全部 msgid，用 ZH_MAP 填入中文翻译生成 zh_CN.po / This script reads all msgid from .pot, uses ZH_MAP to fill Chinese translations for zh_CN.po
  3. en.po 使用 identity（msgstr = msgid） / en.po uses identity (msgstr = msgid)
  4. 之后再执行 pybabel compile 生成 .mo / Then run pybabel compile to generate .mo

用法 / Usage: python3 scripts/gen_i18n_po.py
"""
import os

BASE = os.path.join(os.path.dirname(__file__), "..", "core", "i18n", "locales")
POT = os.path.join(BASE, "messages.pot")

# 英文 msgid → 中文翻译 / English msgid → Chinese translation
ZH_MAP = {
    # admin
    "Please log in to the admin console first": "请先登录管理后台",
    "Admin login expired": "管理员登录已过期",
    "Admin password not configured (ADMIN_PASSWORD)": "管理员密码未配置（ADMIN_PASSWORD）",
    "Incorrect password": "密码错误",
    "Logged out": "已登出",
    "User not found": "用户不存在",
    "Invalid tier, options: {opts}": "无效档位，可选: {opts}",
    "Update failed": "更新失败",
    "Invalid status, options: active, disabled": "无效状态，可选: active, disabled",
    "Invalid type, options: {opts}": "无效类型，可选: {opts}",
    "Invalid target user, options: {opts} or tier:<name>": "无效目标用户，可选: {opts} 或 tier:<name>",
    "Invalid dismissal policy, options: {opts}": "无效关闭策略，可选: {opts}",
    "Message not found": "消息不存在",
    "Identifier name cannot be empty": "标识名不能为空",
    "Invalid effective target, options: all, tier:<name>, users": "无效生效对象，可选: all, tier:<name>, users",
    "Feature flag not found": "功能开关不存在",
    # auth
    "OAuth authorization failed: {err}": "OAuth 授权失败: {err}",
    "Security verification failed, please log in again": "安全验证失败，请重新登录",
    "Missing authorization code": "缺少授权码",
    "Authorization code exchange failed: {err}": "授权码交换失败: {err}",
    "Failed to get user info: {err}": "获取用户信息失败: {err}",
    "Not logged in": "未登录",
    "Login expired, please log in again": "登录已过期，请重新登录",
    # notes
    "Task not found": "任务不存在",
    "Injection content not found": "注入内容不存在",
    "To-do not found": "待办不存在",
    # projects
    "Path not found: {path}": "路径不存在: {path}",
    "Not a directory: {path}": "不是目录: {path}",
    "No permission to access: {path}": "无权限访问: {path}",
    "Folder not found: {path}": "文件夹不存在: {path}",
    "Failed to open folder: {err}": "打开文件夹失败: {err}",
    "Knowledge base name cannot be empty": "知识库名称不能为空",
    "Knowledge base not found": "知识库不存在",
    "Knowledge base or folder not found": "知识库或文件夹不存在",
    "No folders with sync enabled": "没有启用同步的文件夹",
    "Synced {count} meeting(s), wrote {files} file(s)": "已同步 {count} 个会议，写入 {files} 个文件",
    "Index build started": "索引构建已启动",
    # record
    "Already recording": "已在录制中",
    "Failed to start recording: {err}": "录制启动失败: {err}",
    "Not recording": "未在录制中",
    "Failed to stop recording: {err}": "录制停止失败: {err}",
    "Failed to abandon recording: {err}": "放弃录音失败: {err}",
    "No active real-time summary": "无活跃的实时总结",
    "No active recording": "无活跃的录音",
    "Speaker not found": "说话人不存在",
    "Task not found or not recording": "任务不存在或未在录制",
    # settings
    "ASR proxy service connected": "ASR 代理服务连接正常",
    "Connection successful, model {model} responding": "连接成功，模型 {model} 响应正常",
    # speakers
    "Name cannot be empty": "姓名不能为空",
    "Operation failed": "操作失败",
    "Current status does not allow setting speaker mapping": "当前状态不允许设置说话人映射",
    "Task not yet completed": "任务尚未完成",
    "Speaker mapping not set": "未设置说话人映射",
    # tasks
    "Unsupported file type: {ext}": "不支持的文件类型: {ext}",
    "speaker_count must be between 1 and 100": "speaker_count 必须在 1-100 之间",
    "Minutes file not found": "纪要文件不存在",
    "Recording file not found": "录音文件不存在",
    "Recording file not found, cannot re-transcribe": "录音文件不存在，无法重新识别",
    "Transcription result not found, please use Re-transcribe": "转写结果不存在，请使用「重新识别」",
    "Invalid date format, expected YYYY-MM-DD": "日期格式无效，应为 YYYY-MM-DD",
    "Task not completed, cannot sync": "任务未完成，无法同步",
    "Task is not linked to a knowledge base": "任务未关联知识库",
    "Monthly transcription quota exhausted ({remaining} min remaining). Configure your own API Key to continue.": "本月转写额度已用完（剩余 {remaining} 分钟），可配置自有 API Key 继续使用",
    # usage
    "Self-hosted Key, not metered": "自带 Key，不计量",
    # user
    "Please set up your name first": "请先设置用户姓名",
    "Binding failed": "绑定失败",
    "Please log in first": "请先登录",
    # voiceprint
    "Audio file not found: {path}": "音频文件不存在: {path}",
    "Failed to read audio: {err}": "无法读取音频: {err}",
    "Invalid time range": "时间区间无效",
    "Audio too short: {dur}s (minimum {min}s required)": "音频太短: {dur}s（最少需要 {min}s）",
    "Voiceprint extraction failed (audio quality may be insufficient)": "声纹提取失败（音频质量可能不足）",
    "Voiceprint registered: {name}": "声纹注册成功: {name}",
    "Voiceprint not found": "声纹不存在",
    "Voiceprint rebuilt from {count} meeting(s): {name}": "声纹已基于 {count} 场会议重建: {name}",
    "Task has no transcription result yet": "任务尚无转写结果",
    "Normalized audio unavailable": "归一化音频不可用",
    # errors.py
    "Service temporarily unavailable, please try again later.": "服务暂时不可用，请稍后重试。",
    "Audio file issue detected. Please check the file format and integrity.": "音频文件可能有问题，请检查文件格式和完整性后重试。",
    "API configuration error. Please check API Key and account status.": "API 配置异常，请检查 API Key 和账户状态。",
    "No valid speech detected in the audio. Please confirm the recording contains human voice.": "音频中未检测到有效语音片段，请确认录音是否正常、是否包含人声。",
    "Transcription service error. Please try re-transcribing.": "转写服务返回错误，可尝试重新识别。",
    "Processing failed. Please try again. Contact support if the issue persists.": "处理失败，请重试。若问题持续存在请联系支持。",
    # auth (SMS/logout)
    "Please enter a valid phone number": "请输入正确的手机号",
    "Please enter the verification code": "请输入验证码",
    # settings (test connection errors)
    "ASR proxy URL not configured": "未配置 ASR 代理地址",
    "Proxy server has no DASHSCOPE_API_KEY configured": "代理服务端未配置 DASHSCOPE_API_KEY",
    "Proxy signature verification failed": "代理签名校验失败",
    "Connection timeout (15s), please check network": "连接超时（15s），请检查网络",
    "Connection timeout (15s), please check network or Base URL": "连接超时（15s），请检查网络或 Base URL",
    "Cannot connect to {url}, please check the address": "无法连接到 {url}，请检查地址是否正确",
    "Test failed: {err}": "测试失败: {err}",
    "LLM API Key not configured": "未配置 LLM API Key",
    "LLM API Base URL not configured": "未配置 LLM API Base URL",
    "Invalid LLM API Key (401 Unauthorized)": "LLM API Key 无效（401 Unauthorized）",
    "No permission to access LLM service (403 Forbidden)": "无权访问 LLM 服务（403 Forbidden）",
    "Endpoint or model not found (404). Please check Base URL and model name": "端点或模型不存在（404）。请检查 Base URL 和模型名称",
    "Too many requests (429 Rate Limited), the Key itself is valid": "请求过于频繁（429 Rate Limited），Key 本身是有效的",
    # tasks / speakers (response messages)
    "Re-transcription task submitted": "已提交重新识别任务",
    "Regenerating minutes...": "正在重新生成纪要...",
    "Generating minutes...": "正在生成纪要...",
    "No target folder to sync": "没有可同步的目标文件夹",
    "Wrote {count} file(s) to knowledge base folder": "已写入 {count} 个文件到知识库文件夹",
    # chat (HTTP errors)
    "Message cannot be empty": "消息不能为空",
    "AI conversation failed: {err}": "AI 对话失败: {err}",
    "Text cannot be empty": "文本不能为空",
    "Text refinement failed: {err}": "文稿优化失败: {err}",
}

HEADER = '''# {lang} translation for Open Meeting Scribe
# Generated by scripts/gen_i18n_po.py
msgid ""
msgstr ""
"Project-Id-Version: open-meeting-scribe 0.1.0\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: 2026-09-10 00:00+0800\\n"
"PO-Revision-Date: 2026-09-10 00:00+0800\\n"
"Last-Translator: \\n"
"Language-Team: {lang}\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
'''


def po_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def read_msgids(pot_path: str):
    """从 .pot 读取全部非空 msgid（保持顺序） / Read all non-empty msgid from .pot (preserve order)"""
    ids = []
    with open(pot_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("msgid "):
                raw = line[len("msgid "):].strip()
                # 去掉外层引号并反转义 / Strip outer quotes and unescape
                val = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
                if val:
                    ids.append(val)
    return ids


def write_po(path: str, lang: str, msgids, translator):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = [HEADER.format(lang=lang)]
    missing = []
    for mid in msgids:
        zh = translator(mid)
        if zh is None:
            missing.append(mid)
            zh = mid  # 回退到英文 / Fallback to English
        lines.append(f'msgid "{po_escape(mid)}"')
        lines.append(f'msgstr "{po_escape(zh)}"')
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return missing


def main():
    msgids = read_msgids(POT)
    print(f"读取到 {len(msgids)} 个 msgid")

    # zh_CN：用映射表翻译 / zh_CN: translate using mapping
    zh_path = os.path.join(BASE, "zh_CN", "LC_MESSAGES", "messages.po")
    missing = write_po(zh_path, "zh_CN", msgids, lambda m: ZH_MAP.get(m))
    print(f"写入 {zh_path}")
    if missing:
        print(f"  ⚠ {len(missing)} 个 msgid 缺少中文翻译（已回退英文）:")
        for m in missing:
            print(f"    - {m}")

    # en：identity / en: identity
    en_path = os.path.join(BASE, "en", "LC_MESSAGES", "messages.po")
    write_po(en_path, "en", msgids, lambda m: m)
    print(f"写入 {en_path}")


if __name__ == "__main__":
    main()
