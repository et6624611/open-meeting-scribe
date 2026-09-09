import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// 样式引入顺序：
// 1. 主题变量（CSS 自定义属性，必须最先加载）
import './styles/themes/default.css'
import './styles/themes/dark.css'
import './styles/themes/warm.css'
import './styles/themes/forest.css'
import './styles/themes/ocean.css'
import './styles/themes/lavender.css'
import './styles/themes/rose.css'
// 2. 旧版全量 CSS（过渡文件，确保所有视图视觉完整）
import './styles/legacy-views.css'
// 3. 新版模块化 CSS（覆盖 legacy 中的重复规则）
import './styles/base.css'
import './styles/layout.css'
import './styles/topbar.css'
import './styles/sidebar.css'
import './styles/ai-panel.css'
import './styles/components.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
