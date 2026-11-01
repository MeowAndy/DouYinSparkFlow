// 与 Python 侧 app/web/bridge.py 配套的薄封装。
// 页面 -> Python：window.$py(method, payload)，返回值已是 JSON 安全类型；
// Python -> 页面：window.__pyOn(event, data)，由宿主 page.evaluate 推送。
//
// 注意：宿主先加载页面、再暴露桥（暴露在导航前的桥会变成坏的函数），
// 所以页面在桥就绪之前发起的调用要排队，等就绪后统一放行。

import { ElMessageBox } from 'element-plus'

const handlers = new Map()
const pending = []

// 注册在 window 上：主循环用 page.evaluate 调用它推事件
window.__pyOn = (event, data) => {
  const handler = handlers.get(event)
  if (handler) handler(data)
}

function callNow(method, payload) {
  return window.$py(method, payload ?? null).then((res) => {
    if (res && typeof res === 'object' && 'error' in res) {
      const err = new Error(String(res.error))
      err.pyError = true
      throw err
    }
    return res
  })
}

export function py(method, payload) {
  if (typeof window.$py === 'function') return callNow(method, payload)
  return new Promise((resolve, reject) => {
    pending.push({ method, payload, resolve, reject })
  })
}

function flushPending() {
  if (typeof window.$py !== 'function') return
  if (!pending.length) return
  const snapshot = pending.splice(0)
  for (const item of snapshot) {
    callNow(item.method, item.payload).then(item.resolve, item.reject)
  }
}

setInterval(flushPending, 120)

export function on(event, handler) {
  handlers.set(event, handler)
  return () => handlers.delete(event)
}

// ── 运行模式注册：普通方式被系统拒绝时，引导用户用 UAC 提权重试 ──
// 只提权「注册」这一个动作；日常执行任务仍以普通用户身份运行。
export async function applyModeWithElevation(mode) {
  try {
    const res = await py('schedule_set_mode', { mode })
    return { ok: true, schedule: res.schedule }
  } catch (e) {
    const text = String(e.message || e)
    const denied =
      text.includes('拒绝访问') ||
      text.toLowerCase().includes('access is denied') ||
      text.includes('0x80070005')
    if (!denied) return { ok: false, message: text }
  }
  try {
    await ElMessageBox.confirm(
      '当前账户没有创建计划任务的权限。是否弹出系统授权窗口（UAC），以管理员身份完成这一次注册？之后任务的日常执行仍不需要管理员。',
      '需要管理员权限',
      { confirmButtonText: '授权并注册', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return { ok: false, message: '已取消', cancelled: true }
  }
  const res = await py('schedule_elevate_register', { mode })
  if (res.cancelled) return { ok: false, message: '已取消管理员授权', cancelled: true }
  if (!res.ok) throw new Error(res.message || '管理员注册未成功')
  return { ok: true, schedule: res.schedule, elevated: true }
}