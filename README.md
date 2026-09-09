# ConvertTo3D

Vue 3 + JavaScript + Vite 项目骨架，使用 Vue Router 和 Pinia。

## 本地开发

推荐使用 Node.js 22.12+（22 LTS）和 npm。

```sh
npm install
npm run dev
```

根据终端输出的地址访问应用。可将 `.env.example` 复制为 `.env.local` 配置环境变量；`VITE_` 变量会暴露给浏览器，不要存储密钥。`VITE_API_BASE_URL` 为后续接口开发预留，当前未接入后端。

## 常用命令

```sh
npm run build      # 生产构建，产物输出到 dist/
npm run preview    # 本地预览构建产物
```

## 目录结构

```text
public/             原样复制到构建产物的静态资源
src/
  api/              接口请求与业务 API
  assets/           参与构建的图片、字体等资源
  components/       通用组件
  composables/      可复用的组合式函数（useXxx）
  layouts/          页面布局
  router/           路由配置，页面按需加载
  stores/           Pinia 状态管理
  styles/           全局样式
  utils/            纯工具函数
  views/            路由页面
  App.vue           根组件
  main.js           应用入口
index.html          HTML 入口
vite.config.js      Vite 配置与 @ 路径别名
jsconfig.json       编辑器路径别名配置
```

新增页面时，在 `src/views/` 添加 Vue 单文件组件并在 `src/router/index.js` 注册路由。业务状态放在 `src/stores/`，组件使用 `<script setup>`。`@/` 指向 `src/`。

路由使用 HTML5 History 模式，部署时请配置服务器将未匹配的页面路径回退到 `index.html`，API 路径应由后端单独处理。
