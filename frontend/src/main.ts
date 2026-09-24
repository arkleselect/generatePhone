import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
// Mount the single-user workspace with shared Element Plus form controls.
createApp(App).use(ElementPlus).mount('#app')
