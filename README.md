# ConvertTo3D

本地 Inventor 零件转换与二维工程图重建工作台。Vue 3 前端 + Python FastAPI + InventorLoader / FreeCAD 便携运行环境 + LibreDWG + Open CASCADE。

## 当前能力

- 直接上传 IPT，通过项目内的开源转换器读取原有实体并转换为一个 STEP 文件，无需安装或激活 Inventor；IPT 不执行二维截面识别。多实体 IPT 保留所有实体，不强制合并或丢弃。
- 上传 DWG / DXF（最大 100 MB），读取实际几何、图层、布局、文字、尺寸和单位。
- 展开普通块引用，识别闭合区域；标注不参与建模，非 XY 平面和中心/虚线几何不参与轮廓生成。
- 二维轮廓预览、区域选择、单位确认；支持单个闭合区域拉伸或绕 X/Y 方向轴旋转。
- 输出真实 STEP B-rep 实体，保留内环孔洞；自动校验单实体、体积，并回读 STEP 验证。
- 三维预览支持拖动旋转和滚轮缩放；下载 STEP 和建模参数 JSON。
- 所有图纸在本机处理，运行时文件放在 `runtime/jobs/`，不会提交到 Git。任务暂不自动清理。

**这不是任意工程图自动还原系统。** STEP 可在 SolidWorks 中作为实体导入并继续建模，不含原始草图和参数化特征树。原生 SLDPRT 需安装 SolidWorks 后另存；当前机器未检测到 SolidWorks，未验证其原生保存。

## 安装与运行（Windows）

需要 Python 3.13 64 位和支持 Vite 7 的 Node.js。首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
# IPT 转换另行配置便携运行组件（约 484 MB 下载，解压后占用更多空间）：
powershell -ExecutionPolicy Bypass -File scripts/setup-ipt.ps1
# 如官方 PyPI 网络较慢，可选择镜像：
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -PackageIndex https://pypi.tuna.tsinghua.edu.cn/simple
```

脚本将依赖安装到项目 `.venv`，下载 LibreDWG 0.14 Windows x64 到 `tools/libredwg`，并安装前端依赖。也可设置 `DWG2DXF_PATH` 指向自行安装的 `dwg2dxf.exe`。

两个终端分别运行：

```powershell
npm run server
```

```powershell
npm run dev
```

打开 Vite 输出的本地地址。前端通过 `/api` 代理到 `127.0.0.1:8000`；服务仅绑定本机。生产构建及本地预览：`npm run build`、`npm run preview`（仍需启动 Python 后端）。可选前端变量见 `.env.example`。

## 使用

1. 上传 IPT，点击“开始转换”；系统读取原有实体、转换、校验后直接显示三维预览并提供 STEP 下载，无需选择截面。原文件中有多个实体时，全部保存在同一个 STEP 文件中。
2. 如只有二维源文件，可上传 DWG / DXF，点击“解析图纸”。
3. 二维流程中检查布局、单位、图纸比例、文字/尺寸和未支持的对象，并使用整体识别方案或通用特征组合。
4. SolidWorks 2023 中打开 STEP，按需另存为 SLDPRT。项目也提供手动运行的 COM 脚本：

```powershell
powershell -File scripts/save-solidworks.ps1 -StepPath 'D:/models/model.step' -OutputPath 'D:/models/model.sldprt'
```

此脚本需要本机已安装并授权的 SolidWorks，拒绝覆盖现有文件。它只保存导入的实体，不重建特征树；尚未在 SolidWorks 上实测。

## STEP 工程图 PDF

STEP 生成成功后，页面下方显示“STEP → 工程图 PDF”设置区。填写零件名称、图号、单位、材料和技术要求，选择 A3/A4、比例、模型长轴、旋转角度、横截面位置及纵剖偏移，点击“生成工程图 PDF”，即可预览和下载。

- 从实际 STEP 生成主视图、端视图、纵向剖面和横截面；隐藏线可选。剖面线只填充实体材料区域，保留内孔。中心参考线按模型包围盒中心绘制，不代表设计基准。
- 自动尺寸覆盖外形尺寸及可识别的完整横截面圆径，测量值来自实体几何。矢量曲线以最大 0.025 mm 模型空间偏差离散；PDF 不是三维预览截图。
- 公差、粗糙度、材料、螺纹规格和热处理等设计要求不从几何猜测，需要填写。当前不自动生成完整加工尺寸链、形位公差框、局部放大图或装配明细表；不能视为原始五页参考图纸的自动恢复。
- 固定比例无法放入图框、剖切平面没有材料或技术要求文字超出图框时返回明确错误，不会静默裁掉内容。更改设置后需重新生成，避免下载旧设置的图纸。
- PDF 和设置 JSON 按独立版本保存在原模型任务目录内。接口：`POST /api/drawings/{job}/outputs/{generation}/engineering-pdf`；响应包含 `pdfUrl`，追加 `?download=true` 下载，否则在线预览。
- 依赖已加入 `backend/requirements.txt`，现有环境升级后需重新安装该文件中的依赖并重启后端。中文优先嵌入系统宋体；没有宋体时使用标准中文 CID 字体。

## 样例结论与限制

- IPT 使用 FreeCAD 0.21.2 和 InventorLoader 提交 `e94bdf5e29052a0dc7ce6fdf755e956ae507caec`，依赖只放在项目 `tools` 内。安装脚本校验下载归档 SHA-256；InventorLoader 源码及 GPL-2.0 许可证随归档保留，FreeCAD 和其他依赖保留各自许可证。
- 已通过真实上传接口测试“下接头”（1 个实体、21 个面）、“中部连接头”（1 个实体、54 个面）、“下接头 -2”（2 个实体、42 个面），均输出一个 STEP 文件；检查面数、实体有效性及 STEP 回读体积。
- 开源 IPT 支持范围有限；暂不支持多个候选实体数据集、一个实体包含多个边界壳及无法转换的面/边。检测到缺面、缺边、解析错误或非闭合实体时拒绝输出，不承诺支持任意 IPT。转换超时 240 秒，不保留原始参数化特征历史。
- 可选真实样件回归：设置 `IPT_SAMPLE_DIR` 为上述三个 IPT 文件的目录，再执行 `npm run test:backend`。未设置时跳过真实样件测试，普通单元测试不能证明 IPT 转换成功。

用户提供的“母扣零件.DWG”已实际解析：21 个图元、毫米单位、无文字或尺寸标注，是筒状带内螺纹零件的轴测投影。**不能仅凭所识别闭合区域准确还原该母扣。** 详见 `docs/sample-findings.md`。

- 通用模式支持多个闭合截面的拉伸、旋转、加料和切除，可来自不同布局，通过视图原点与 XY / XZ / YZ 平面放置到统一坐标系；最多 32 个特征，最终必须为一个实体。
- 自动识别覆盖具有尺寸证据的同轴台阶零件正视图/右侧视图组合，以及左侧对称轴向剖面/右侧端面组合（含轴线上下成对的盲孔）。其他形状使用通用特征组合，人工指定截面、尺寸和视图对应关系。尚不支持任意工程图全自动还原、放样、扫掠、自由曲面或真实螺纹。
- 圆保持解析圆；样条、圆弧等以 0.01 图纸单位离散。已有多段线按原始顶点处理。
- 不自动跨间隙补线；无法形成闭合区域时需要在 CAD 中修复。
- 输出有效性校验只证明实体在几何上有效，不证明它等于原设计或可用于制造。
- 外部参照、代理对象等未支持内容不会加载；解析概况会报告未参与建模的对象。
- 大型图纸暂不支持：单布局最多 30,000 图元，最多返回 500 个候选区域；转换超时 90 秒。仅供可信本地图纸使用。

## 接口

### IPT 输出选择（当前部分实现）

上传 IPT 前可选择 STEP 或原始参数化 SLDPRT。STEP 保持现有转换和工程图 PDF 功能；SLDPRT 明确标为“尚不可用”，选择后不能提交。**此版本只完成格式选择和请求校验，未实现原始草图、尺寸约束及特征历史迁移，也没有生成可编辑的 SLDPRT。**

`POST /api/drawings` 增加 multipart 字段 `outputFormat`，默认 `step` 兼容原调用。请求 `sldprt` 时返回 503 并说明未实现，不执行 STEP 转换、不创建任务或返回替代文件；非 IPT 请求该格式返回 422。`GET /api/health` 的 `iptParametric` 提供实际可用状态及原因。

现有 InventorLoader 原生特征策略仍有未支持的约束，当前项目采用的是 ACIS 几何路径，且没有原生 SLDPRT 写入器。本机也未检测到 SolidWorks COM 注册接口。安装软件本身并不证明完整迁移已经可用；后续必须实现源参数读取、特征依赖映射、原生写入，并对样件逐项检查约束、历史及改尺寸后的重建结果。

可进一步验证的原生路径：[SOLIDWORKS 2025 Inventor 文件导入说明](https://help.solidworks.com/2025/English/SolidWorks/sldworks/t_Autodesk_Inventor_Files.htm?format=P&value=)明确区分几何导入和特征导入，后者支持部分草图、草图尺寸及建模特征并保留历史，要求安装 Inventor；未识别特征会转为实体。该说明不是所有原始尺寸约束无损迁移的保证。需要在有授权且版本兼容的 SolidWorks / Inventor 转换环境中对三个样件验证；当前尚无该运行环境，未实现或验证自动化调用。

[SOLIDWORKS LoadFile4 官方文档](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~LoadFile4.html)说明常用导入路径产生无特征历史的几何实体，因此不能把导入后另存或 FeatureWorks 几何识别当作原始历史迁移。此处不接入外部转换服务，不上传原文件。

- `GET /api/health`：CAD 依赖状态。
- `POST /api/drawings`：multipart `file` 上传；返回任务 ID、布局、几何和候选区域。
- `POST /api/drawings/{id}/generate-features`：通用特征序列组合，校验单实体并输出来源轮廓和建模记录。
- `POST /api/drawings/{id}/generate-part`：生成经过确认的自动识别方案。
- `POST /api/drawings/{id}/generate`：确认布局/区域/单位/操作及参数，返回 STEP、STL 预览及 JSON 下载地址。
- `GET /api/drawings/{id}/outputs/{generationId}/{filename}`：读取该次生成结果。

每次生成使用独立目录，修改参数会使界面中的旧结果失效。API 不接受客户端提交的任意几何或文件路径，仅使用服务端解析的轮廓。

上传 IPT 时，同一接口直接返回 `sourceType: inventor-part` 及已验证的 `result`。转换只读取上传任务目录中的源文件，并输出到该任务目录；要求转换后的 STEP 恰好包含一个有效实体。IAM 装配体目前不在支持范围内。

## 验证

```powershell
npm run test:backend
npm run build
```

后端测试覆盖带孔精确圆拉伸、旋转体积和轴穿越拒绝、单位换算、开放轮廓拒绝、非平面图元排除、块引用变换，以及存在本地样例时的实际 DWG 回归。

## 技术参考

- [LibreDWG 官方项目与 GPL-3.0 许可](https://github.com/LibreDWG/libredwg)。下载工具及其许可留在本地 tools 目录，不包含在本项目 Git 中；发布产品时需审查依赖分发许可。
- [ezdxf Path API](https://ezdxf.readthedocs.io/en/stable/path.html)
- [Open CASCADE 建模](https://dev.opencascade.org/doc/refman/html/package_brepprimapi.html)
- [SolidWorks 2023 STEP 导入 API](https://help.solidworks.com/2023/english/api/sldworksapi/import_step_file_example_vb.htm)

## 通用性与测试样件

Drawing1.dwg 仅用于回归验证，不以文件名选择建模逻辑。识别器读取实际圆、边线与尺寸证据；通用特征引擎不依赖端盖识别器。独立合成测试覆盖矩形实体、侧向孔、顶部凸台、不相交切除和多实体拒绝。测试样件已按用户指定将 M5 简化为公称直径通孔、省略 R3；此选择不代表其他图纸的设计要求。

视图原点 U/V 使用图纸坐标，实体位置 X/Y/Z 和拉伸深度使用毫米。XY 法向 +Z，XZ 法向 −Y，YZ 法向 +X。旋转轴坐标以原始二维视图为准。组合不自动推断视图间比例，比例不同的视图需先统一。

喷嘴剖面回归：`喷嘴-删除内容测试版.dwg` 可识别为总长 15 mm 的一个实体。先合并被孔和螺纹表示线分割的主体剖面，再按端面孔位切除两个盲孔，保留中心流道和外形环槽。孔径采用端面圆 Ø5.5（剖视绘制为 Ø5.2），含钻尖总深约 8.001 mm；差异在生成前显示。外螺纹使用公称外形，流道圆弧沿用 0.01 图纸单位离散。识别不依赖文件名；缺失尺寸、孔位证据或剖面不对称时不提供该自动方案。已有上传任务需重新解析，后端需重启以加载修改。
