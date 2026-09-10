/**
 * 自定义 ESLint 规则：require-button-label
 *
 * 禁止无文本定义的图标按钮——所有 <button> 必须具备以下至少一项：
 *   1. title / aria-label / data-tip 属性（含动态绑定 :title 等）
 *   2. 标签内有可见文本内容（非纯空白）
 *
 * 违反此规则的按钮 = 用户无法理解其功能 = 不可变更原则违规。
 */

/**
 * 递归遍历 Vue 模板 AST，查找所有 <button> 元素
 */
function findButtons(node, results = []) {
  if (!node) return results

  if (node.type === 'VElement' && node.name === 'button') {
    results.push(node)
  }

  if (node.children) {
    for (const child of node.children) {
      findButtons(child, results)
    }
  }

  return results
}

/**
 * 检查元素是否有 label 属性（title / aria-label / data-tip，含动态绑定 :title 等）
 */
function hasLabelAttribute(node) {
  const labelAttrs = ['title', 'aria-label', 'data-tip']
  return (node.startTag?.attributes || []).some((attr) => {
    if (!attr.key) return false

    // 普通属性：title="xxx"
    if (attr.key.type === 'VIdentifier') {
      return labelAttrs.includes(attr.key.name)
    }

    // 动态绑定：:title="xxx" 即 v-bind:title="xxx"
    if (attr.key.type === 'VDirectiveKey') {
      const directiveName = attr.key.name?.name || ''
      const argumentName = attr.key.argument?.name || ''
      // :title / :aria-label / :data-tip
      if (directiveName === 'bind' && labelAttrs.includes(argumentName)) {
        return true
      }
    }

    return false
  })
}

/**
 * 检查元素内部是否有可见文本内容
 */
function hasVisibleTextContent(node) {
  if (!node.children || node.children.length === 0) return false

  for (const child of node.children) {
    // VText 节点：检查是否有非空白文本
    if (child.type === 'VText' && child.value && child.value.trim().length > 0) {
      return true
    }
    // VExpressionContainer（如 {{ label }}）视为有文本
    if (child.type === 'VExpressionContainer') {
      return true
    }
  }
  return false
}

const rule = {
  meta: {
    type: 'problem',
    docs: {
      description: '禁止无文本定义的图标按钮：所有 <button> 必须有 title/aria-label/data-tip 或可见文本',
      recommended: true,
    },
    messages: {
      missingLabel:
        '图标按钮缺少文本定义。必须提供 title、aria-label 或 data-tip 之一，或在按钮内添加可见文本。推荐使用 IconButton 组件（label 为必填 prop）。',
    },
    schema: [],
  },

  create(context) {
    return {
      Program(node) {
        // 获取 Vue 模板 AST
        const templateBody = node.templateBody
        if (!templateBody) return

        // 查找所有 <button> 元素
        const buttons = findButtons(templateBody)

        for (const button of buttons) {
          // 有 label 属性 → 合规
          if (hasLabelAttribute(button)) continue

          // 有可见文本内容 → 合规
          if (hasVisibleTextContent(button)) continue

          // 既无 label 属性，又无文本内容 → 违规
          context.report({
            loc: button.loc || button.startTag.loc,
            messageId: 'missingLabel',
          })
        }
      },
    }
  },
}

export default rule
