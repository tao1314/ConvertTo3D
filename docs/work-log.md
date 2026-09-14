## 2026-09-11（工作记录-补充3）

一、问题概述

用户再次明确 SLDPRT 必须能够实际转换，不接受只提供不可用选项；该要求仍未完成。

二、处理内容

- README.md：补充核实到的 SOLIDWORKS 官方 Inventor 特征导入路径、Inventor 安装要求及未识别特征降级为实体的限制。
- 不继续增加占位转换代码，也不将几何导入或自动识别特征作为原始草图、约束和历史迁移。

三、验证结果（含涉及文件）

- 官方文档支持把原生特征导入作为后续验证方向，但没有证明全部原始约束可无损迁移。当前没有可运行该流程的 SolidWorks / Inventor 环境，尚不能输出和验收用户要求的 SLDPRT。
- 本次仅更新 README.md 与本工作记录，没有新的转换结果或运行测试。

## 2026-09-11（工作记录-补充2）

一、问题概述

用户要求保留 IPT 转 STEP，同时可选择迁移原始草图、尺寸约束和特征历史并输出可编辑 SLDPRT。本次仅完成输出选项及能力校验，核心参数化迁移尚未实现，不能视为需求已完成。

二、处理内容

- src/components/IptOutputFormat.vue：新增独立输出选择组件，说明 STEP 的几何范围和 SLDPRT 尚不可用状态。
- src/views/HomeView.vue：接入选择组件、上传格式字段及不可用格式提交拦截；纠正另存 SLDPRT 即能恢复原始历史的歧义。
- backend/app.py：上传增加 outputFormat 字段，默认 STEP 保持兼容；SLDPRT 请求明确返回 503，不创建任务、不降级转换；健康接口公开不可用原因。
- backend/inventor.py：集中定义参数化迁移尚未实现的说明，原有 STEP 转换函数不变。
- backend/tests/test_api.py：验证显式 STEP、未知格式、非 IPT 选择 SLDPRT，以及拒绝后没有几何转换和任务残留。
- README.md：记录部分实现状态、接口行为及后续需要完成的参数读取、依赖映射、原生写入和编辑重建校验。

三、验证结果（含涉及文件）

- 30 项后端测试通过，包含三个真实 IPT 样件回归；前端构建通过（43 个模块）；git diff --check 通过。
- 检查本机 SldWorks.Application 与 Inventor.Application 注册路径未找到接口。现有 InventorLoader 源码含多项未支持约束；当前项目没有原生 SLDPRT 写入器。官方 LoadFile4 文档说明常见导入路径为无特征历史几何，不能据此实现原始历史迁移。
- 未生成或验证任何新的 SLDPRT，未宣称保留原始约束或特征历史；没有将文件发送外部服务。前端此次仅完成构建验证，未做浏览器交互验收；运行中的后端需重启加载新接口。

## 2026-09-11（工作记录-补充1）

一、问题概述

新增由已转换 STEP 生成工程图 PDF 的功能；后续用户反馈 STEP 在 SolidWorks 中不能编辑，需要进一步区分实体导入异常与缺少参数化特征历史。

二、处理内容

- backend/engineering_pdf.py：新增矢量投影、真实平面剖切、材料区域剖面线、几何外形尺寸与圆径标注、中文图框和技术要求排版。
- backend/pdf_routes.py、backend/app.py：新增工程图设置校验、独立版本生成、PDF 回读、预览及下载接口。
- src/components/EngineeringDrawing.vue、src/views/HomeView.vue：新增独立工程图设置组件，支持图幅、比例、方向、旋转、剖切位置、标题栏及说明填写；生成后提供内嵌预览和下载。
- backend/requirements.txt：新增 reportlab 与 pypdf；backend/tests/test_engineering_pdf.py、backend/tests/test_api.py 增加剖切孔洞、材料面积、尺寸及 HTTP 下载验证；README.md 记录使用方式和支持范围。

三、验证结果（含涉及文件）

- 29 项后端测试通过，包含真实 IPT 回归；前端构建通过。三个已有 STEP 样件均生成四视图 PDF，A3 与 A4 排版已渲染检查。
- 浏览器实际完成 IPT 上传、STEP 转换、工程图生成，确认内嵌 PDF 显示完整图纸并提供下载入口。本地服务已加载 PDF 接口。
- 示例输出：output/pdf/下接头-工程图.pdf。自动尺寸限于外形尺寸及可识别完整圆径，不自动恢复原图公差、全部加工尺寸、局部放大图和装配明细。
- 浏览器保留预览标签页的动作被自动审批拒绝，提示用量上限；未尝试绕过，不影响已生成 PDF 和本地服务。
- 当前 IPT 转 STEP 路径保留实体几何，不保留 Inventor 草图、约束及参数化特征历史。用户反馈的 SolidWorks 编辑问题尚未取得导入状态或具体报错，不能据此认定几何无效，也不能宣称参数化编辑已实现。

## 2026-09-10（工作记录-补充7）

一、问题概述

实现上传 IPT 后不依赖 Autodesk Inventor 的本地 STEP 转换，并使用真实样件验证完整模型、预览和下载。

二、处理内容

- backend/inventor.py：用项目内 FreeCAD Python 启动独立转换进程，替换 Inventor COM 调用；增加环境检测、隔离副本、240 秒超时和失败诊断。
- scripts/convert-ipt-open.py：调用 InventorLoader 的嵌入几何读取与 STEP 导出，配置无窗口运行；只解析实体几何段，不重建特征树；拒绝缺面、缺边、解析错误、未闭合实体和不支持的壳结构。校验源面数、实体有效性及最终 STEP 回读体积。
- backend/modeling.py：IPT 路径保留源文件内的全部实体；二维建模仍要求单实体。拒绝实体之外的独立曲面，回读时核对实体数和体积。
- backend/app.py：转换记录说明改为一个 STEP 文件保留源实体，记录开源转换器名称。
- src/views/HomeView.vue：移除必须安装 Inventor 的提示；防止二维参数监听器清空 IPT 转换结果，更新成功提示。
- scripts/setup-ipt.ps1、.gitignore、README.md：增加固定版本、SHA-256 校验的便携环境配置脚本，排除工具缓存，记录安装、实际支持范围及依赖许可证。
- backend/tests/test_api.py：增加可选真实样件上传、下载和几何完整性测试；未提供样件环境时明确跳过。

三、验证结果（含涉及文件）

- 设置 IPT_SAMPLE_DIR 后运行 npm run test:backend：25 项全部通过，包含三个真实 IPT 的 HTTP 上传与 STEP/STL 下载；npm run build、git diff --check、Python 语法检查和安装脚本 PowerShell 语法检查通过。
- 下接头：21 个面、1 个有效实体、体积 2261392.159553 mm³；中部连接头：54 个面、1 个有效实体、体积 2063105.158902 mm³；下接头 -2：42 个面、2 个有效实体、总体积约 2214689.020389 mm³。每个 IPT 输出一个 STEP 文件，不丢弃第二个实体。
- 浏览器实际选择“下接头 -2.ipt”、点击开始转换，页面显示三维预览、2 个实体、体积和 STEP 下载链接，无需选择二维截面；已截图目视核验模型显示。
- 已重启本地后端，/api/health 报告 inventorImporter=true，含义为开源 IPT 转换环境就绪，不表示安装了 Inventor。
- 三个可查看输出保存在 runtime/ipt-results/下接头.step、runtime/ipt-results/中部连接头.step、runtime/ipt-results/下接头 -2.step。用户原文件未修改、未上传第三方服务。
- 限制：这是已通过上述样件的开源转换实现，并非任意 IPT 的完整兼容保证；不保留参数化特征历史，不强制将原有多个实体融合为一个实体。便携组件已实际运行；新增安装脚本完成语法及归档哈希核对，未另行执行全新机器安装测试。

## 2026-09-10（工作记录-补充6）

一、问题概述

重新评估上传 IPT 后不依赖 Inventor 转换为 STEP 的可行性，不以现有 COM 实现的限制作为格式能力结论。

二、处理内容

- 确认现有 backend/inventor.py 的安装检查属于当前实现依赖，并非 IPT 格式必须通过 Inventor 读取。
- 核查 CAD Exchanger 官方 IPT-to-STEP 与 SDK 页面：提供独立转换库，可在应用后端集成；需要 SDK 授权和部署，不能等同于零依赖或免费方案。
- 核查 InventorLoader 官方说明：支持通过嵌入 ACIS 几何转换 STEP，不依赖 Inventor，但需要 FreeCAD 环境；存在曲面与曲线支持限制，不能承诺所有样件完整转换。
- 建议流程为 IPT 上传、独立引擎读取实体、STEP 导出、几何完整性校验、下载；不经过二维截面建模。

三、验证结果（含涉及文件）

- docs/work-log.md：记录可行性结论与来源。
- 官方来源：https://cadexchanger.com/ipt-to-step/ 、https://cadexchanger.com/products/sdk/ 、https://github.com/jmplonka/InventorLoader 。
- 本次仅完成技术路线核查，未修改业务代码、未运行样件转换，尚不能宣称项目已具备该能力。

## 2026-09-10（工作记录-补充5）

一、问题概述

用户将 IPT 转换的输出目标调整为 STEP/STP，当前机器未安装 Inventor 或 SolidWorks，要求无需安装这些软件完成转换。

二、处理内容

- 调查开源 InventorLoader 的 IPT 读取和 STEP 导出实现；该实现依赖 FreeCAD 的几何类型与运行环境，不能直接作为当前 Python 后端的独立转换器使用。
- 使用 olefile 读取三个实际样件的 RSeDb 版本字段：下接头和中部连接头为内部主版本 17，下接头 -2 为内部主版本 24。这只验证容器及版本信息，不代表实体几何已成功解析。
- 未接入未经实际样件验证的转换路径；现有 Inventor 转 STEP 实现仍然依赖本机 Inventor。此次不宣称已完成无 Inventor 的 IPT 转 STEP 功能。

三、验证结果（含涉及文件）

- docs/work-log.md：记录目标变化、调研结果和实际限制。
- 尚未生成并验证任何样件的 STEP 实体；功能未完成。后续需要可运行的 IPT 几何读取引擎，并通过完整性、闭合实体和体积检查，才可提供转换下载。

## 2026-09-10（工作记录-补充4）

一、问题概述

选择一个 IPT 后，按钮“导入完整零件”容易被理解为还需再次上传文件；同时前端在 Inventor 不可用时直接禁用按钮，用户无法获得准确的接口错误。

二、处理内容

- src/views/HomeView.vue：IPT 选择成功后提示“点击开始转换读取该零件”，按钮改为“开始转换”，处理中显示“正在读取完整零件”；移除 IPT 的前端依赖禁用，让后端返回明确的 Inventor 环境诊断。

三、验证结果（含涉及文件）

- npm run build、npm run test:backend、git diff --check：通过。
- 当前服务健康状态为 inventorImporter=false；选择 IPT 后现在可以点击“开始转换”，接口会准确提示本机未检测到 Autodesk Inventor，而不会再表现为要求上传另一个“完整文件”。

## 2026-09-10（工作记录-补充3）

一、问题概述

确认新的输入文件是 Inventor 原生 IPT 三维零件。原页面只接收 DWG/DXF 并要求选择二维截面，不符合直接导入完整零件的需求。

二、处理内容

- backend/inventor.py、scripts/convert-inventor.ps1：验证 IPT 复合文档文件头，通过本机 Inventor COM 打开完整零件并导出 STEP；转换进程保持隐藏并在结束时关闭文档和 Inventor。
- backend/app.py、backend/modeling.py：上传接口接收 IPT，直接转换、回读、验证单实体并生成 STL 预览和下载结果；健康接口报告 Inventor 可用状态。
- src/views/HomeView.vue：IPT 进入完整零件流程，隐藏所有二维截面选项并直接显示三维结果；页面提示 Inventor 依赖。DWG/DXF 流程继续兼容。
- backend/tests/test_inventor.py、backend/tests/test_api.py：覆盖 IPT 文件头校验、完整零件接口响应、结果下载及无效 IPT 拒绝。
- README.md：更新产品定位、IPT 使用方式、依赖和接口行为。

三、验证结果（含涉及文件）

- 三个用户样件“下接头.ipt”“中部连接头.ipt”“下接头 -2.ipt”均为有效 OLE/CFB Inventor 容器，大小分别为 212992、301056、370688 字节。
- npm run test:backend、npm run build、git diff --check：通过。
- 当前机器未检测到 Autodesk Inventor，不能在此环境实际打开三个零件并验证转换后的体积；应用会禁止 IPT 导入并明确提示安装和激活 Inventor，不会回退到二维截面生成。

## 2026-09-10（工作记录-补充2）

一、问题概述

喷嘴-删除内容测试版.dwg 解析出 82 个图元、16 个闭合区域，但旧识别器未关联左侧轴向剖面与右侧端面，无法直接生成完整零件。

二、处理内容

- backend/axial.py：新增对称剖面、轴线、轴向尺寸和端面圆联合识别；合并主体区域后旋转，按端面孔位重建盲孔及钻尖，复用公共轮廓建模和 STEP 单实体导出校验。不依赖样例文件名。
- backend/multiview.py、backend/modeling.py：接入整体轴向剖面方案，不改变原台阶与通用特征流程。
- backend/drawing.py、src/views/HomeView.vue：更新自动识别范围和整体方案展示，显示盲孔深度、孔径差异及外螺纹简化说明。
- backend/tests/test_axial.py、backend/tests/test_api.py：增加实际 DWG、合成平移样件、体积与单位缩放、盲孔底部/非孔方位/环槽/流道空间检查，以及缺尺寸、缺孔位、不对称拒绝和 HTTP 生成下载回归。
- README.md：说明支持范围、喷嘴采用值及重新解析要求。

三、验证结果（含涉及文件）

- npm run test:backend：21 项测试全部通过，包括真实喷嘴 DWG 转换、建模、STEP 回读与空间点检查。
- npm run build、git diff --check：通过。
- runtime/nozzle/model.step、preview.stl、recipe.json、drawing.json、converted.dxf：本地实际样例产物（不提交 Git）。单实体有效，体积约 24256.281 mm³，总长 15 mm；两个 Ø5.5 盲孔含钻尖总深约 8.001 mm。
- 外螺纹未生成螺旋牙型；流道圆弧按现有解析精度离散；孔径采用端面 Ø5.5 并明确提示剖面 Ø5.2 差异。几何验证不代表恢复了原始 CAD 特征树。

## 2026-09-10（工作记录-补充1）

一、问题概述

核对项目默认开发规则，确保后续代码修改遵循用户配置。

二、处理内容

读取根目录 AGENTS.md、package.json、.vscode/extensions.json，检查项目及上级目录规则文件和已有工作记录。未找到现有工作记录，创建本文件。未修改业务代码或开发配置。

三、验证结果（含涉及文件）

- AGENTS.md：确认组件职责分离、函数及模块注释、局部格式化、公共能力复用、最小修改范围、工作记录、修改清单及固定结束语要求。
- package.json、.vscode/extensions.json：未配置格式化命令或格式化器；未发现独立 Prettier、ESLint、EditorConfig 配置。后续沿用目标文件风格，仅格式化本次修改范围。
- docs/work-log.md：新增本次核查记录。仅文档变更，未运行业务测试。
