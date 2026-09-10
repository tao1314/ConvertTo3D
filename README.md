# ConvertTo3D

本地 Inventor 零件转换与二维工程图重建工作台。Vue 3 前端 + Python FastAPI + Autodesk Inventor + LibreDWG + Open CASCADE。

## 当前能力

- 直接上传 Inventor IPT 零件，通过本机 Inventor 读取完整实体并转换为 STEP；IPT 不执行二维截面识别。
- 上传 DWG / DXF（最大 100 MB），读取实际几何、图层、布局、文字、尺寸和单位。
- 展开普通块引用，识别闭合区域；标注不参与建模，非 XY 平面和中心/虚线几何不参与轮廓生成。
- 二维轮廓预览、区域选择、单位确认；支持单个闭合区域拉伸或绕 X/Y 方向轴旋转。
- 输出真实 STEP B-rep 实体，保留内环孔洞；自动校验单实体、体积，并回读 STEP 验证。
- 三维预览支持拖动旋转和滚轮缩放；下载 STEP 和建模参数 JSON。
- 所有图纸在本机处理，运行时文件放在 `runtime/jobs/`，不会提交到 Git。任务暂不自动清理。

**这不是任意工程图自动还原系统。** STEP 可在 SolidWorks 中作为实体导入并继续建模，不含原始草图和参数化特征树。原生 SLDPRT 需安装 SolidWorks 后另存；当前机器未检测到 SolidWorks，未验证其原生保存。

## 安装与运行（Windows）

需要 Python 3.13 64 位和支持 Vite 7 的 Node.js。直接导入 IPT 还需要本机安装并激活 Autodesk Inventor。首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
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

1. 优先上传 IPT，点击“导入完整零件”；系统通过 Inventor 转换、校验后直接显示三维预览并提供 STEP 下载，无需选择截面。
2. 如只有二维源文件，可上传 DWG / DXF，点击“解析图纸”。
3. 二维流程中检查布局、单位、图纸比例、文字/尺寸和未支持的对象，并使用整体识别方案或通用特征组合。
4. SolidWorks 2023 中打开 STEP，按需另存为 SLDPRT。项目也提供手动运行的 COM 脚本：

```powershell
powershell -File scripts/save-solidworks.ps1 -StepPath 'D:/models/model.step' -OutputPath 'D:/models/model.sldprt'
```

此脚本需要本机已安装并授权的 SolidWorks，拒绝覆盖现有文件。它只保存导入的实体，不重建特征树；尚未在 SolidWorks 上实测。

## 样例结论与限制

用户提供的“母扣零件.DWG”已实际解析：21 个图元、毫米单位、无文字或尺寸标注，是筒状带内螺纹零件的轴测投影。**不能仅凭所识别闭合区域准确还原该母扣。** 详见 `docs/sample-findings.md`。

- 通用模式支持多个闭合截面的拉伸、旋转、加料和切除，可来自不同布局，通过视图原点与 XY / XZ / YZ 平面放置到统一坐标系；最多 32 个特征，最终必须为一个实体。
- 自动识别覆盖具有尺寸证据的同轴台阶零件正视图/右侧视图组合，以及左侧对称轴向剖面/右侧端面组合（含轴线上下成对的盲孔）。其他形状使用通用特征组合，人工指定截面、尺寸和视图对应关系。尚不支持任意工程图全自动还原、放样、扫掠、自由曲面或真实螺纹。
- 圆保持解析圆；样条、圆弧等以 0.01 图纸单位离散。已有多段线按原始顶点处理。
- 不自动跨间隙补线；无法形成闭合区域时需要在 CAD 中修复。
- 输出有效性校验只证明实体在几何上有效，不证明它等于原设计或可用于制造。
- 外部参照、代理对象等未支持内容不会加载；解析概况会报告未参与建模的对象。
- 大型图纸暂不支持：单布局最多 30,000 图元，最多返回 500 个候选区域；转换超时 90 秒。仅供可信本地图纸使用。

## 接口

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
