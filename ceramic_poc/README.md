# 瓷砖小样本异常检测 PoC

使用少量正常图片建立 Anomalib PatchCore 特征库，输出原始异常评分、热力图和 OK/NG。训练不使用缺陷图片，不进行梯度优化，不需要指定训练轮数。

本项目独立放在 generatePhone/ceramic_poc；图片生成复用上层系统已经配置好的本机 CLIProxyAPI 账号服务。原火腿肠项目无需改动。

## 环境和启动

已锁定 Python 3.11、Anomalib 2.6.2、PyTorch 2.8.0、torchvision 0.23.0；全部依赖版本保存在 uv.lock。实际代码调用已安装版本的 `anomalib.models.image.patchcore.torch_model.PatchcoreModel`，不手写替代算法。

在本项目目录执行：

```sh
uv sync --python 3.11
uv run ceramic-poc ui --dataset ../datasets/ceramic_tile_phase1
```

打开 http://127.0.0.1:7860 。界面支持查看数据、导入图片目录、设置特征库参数、流式训练日志、加载模型、检测和最终测试评估。

Windows PowerShell + RTX 3080：

```powershell
cd C:\your-path\generatePhone\ceramic_poc
uv sync --python 3.11 --extra cuda
uv run --extra cuda python -c "import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
uv run --extra cuda ceramic-poc ui --dataset ..\datasets\ceramic_tile_phase1
```

Windows 的 cuda extra 从官方 cu128 索引安装 PyTorch；需要支持 CUDA 12.8 的 NVIDIA 驱动。GPU 检查失败时先处理驱动/安装，不能把 CPU 时间当成 RTX 3080 时间。本机为 Apple Silicon Mac，Windows 和 RTX 3080 的实际运行待在目标设备验证。

首次训练需要联网下载 ImageNet 预训练权重；已有项目模型包含完整特征提取权重，加载无需再次下载。网页只绑定 127.0.0.1，不共享到公网。

## 生成和导入

先启动上层 generatePhone 的 Java 服务，在账号设置连接已有账号；不启动旧批次。CLIProxyAPI 位于 127.0.0.1:8317。生成程序读取已有本机客户端密钥，不要求 OpenAI API Key，不在日志中打印密钥。

```sh
uv run ceramic-poc plan ../datasets/ceramic_tile_phase1 --phase 1
uv run ceramic-poc generate ../datasets/ceramic_tile_phase1 --limit 1
uv run ceramic-poc generate ../datasets/ceramic_tile_phase1
uv run ceramic-poc validate ../datasets/ceramic_tile_phase1
```

目录已存在时不要重新 plan；generate 会跳过已有成功结果。原始返回文件在 originals/，独立 1024×1024 PNG 在 train/val/test。服务可能忽略请求尺寸，实际尺寸和统一缩放记录在 receipts.json。不会把缺失结果、拒绝或超时冒充成功；不确定提交标记 UNKNOWN，不自动重新消费额度，需检查现有结果后人工恢复。REJECTED 需处理登录、额度或参数问题后确认是否重试。

提示词在 prompts/；生成计划、每张完整提示词和 metadata.csv 可导出后手动生图再导入，不依赖生图服务才能训练。seed 列留空代表平台未返回实际生图种子；planning_seed 只控制计划参数，不能当作模型生图种子。

第一阶段 20 张正常、4 张划痕、3 张裂纹、3 张污渍，共 30 张：

| 集合 | 正常 | 缺陷 |
|---|---:|---:|
| train | 12 | 0 |
| val | 4 | 6 |
| test | 4 | 4 |

划痕 2/2、裂纹 2/1、污渍 2/1 分到 val/test。底图及其所有衍生图片只属于一个集合。缺陷图从对应集合的正常底图编辑。PNG 和原始提示词只是候选数据，必须观察正常图是否干净、缺陷是否符合类别及严重程度。

局部编辑提示词不能保证平台保留所有未编辑像素。本版本没有将编辑区域当成真实缺陷掩码，也不把生成种子和实际模型信息猜填。编辑前后的外观差异必须检查，合成图成绩不等于真实产线成绩。

导入自有图片时准备如下目录和 CSV，再执行：

```text
dataset/
  train/good/*.png
  val/good/*.png
  val/bad/*.png
  test/good/*.png
  test/bad/*.png
  metadata.csv
```

CSV 列：id,file,label,defect_type,prompt,base_id,seed,split,batch,source_type。label 取 good/bad，split 取 train/val/test；正常 defect_type 为 good。file 为相对路径，base_id 表示最早的独立原始图片来源，不能让同源图片跨集合。AI 图片要求 1024×1024 PNG；真实 MVTec 图片保留原始尺寸。

```sh
uv run ceramic-poc import C:/incoming/images ../datasets/imported_tiles
```

拒绝覆盖目标目录；先完整校验再复制。校验包括缺陷训练禁入、来源泄漏、路径越界、解码像素完全重复、图片格式尺寸。近重复检查采用 32×32 灰度平均绝对差，跨集合差值小于 2 会报告待检查；白色瓷砖可能天然相似，不能将这种启发式结果直接当成重复证据。

## 训练、阈值和测试

```sh
uv run ceramic-poc train ../datasets/ceramic_tile_phase1 runs/phase1_256 --size 256 --ratio 0.01 --device auto
uv run ceramic-poc calibrate runs/phase1_256/model.pt ../datasets/ceramic_tile_phase1
uv run ceramic-poc evaluate runs/phase1_256/calibrated.pt ../datasets/ceramic_tile_phase1 runs/phase1_256_test
uv run ceramic-poc predict runs/phase1_256/calibrated.pt ../datasets/ceramic_tile_phase1/test/bad/scratch_0003.png runs/example_detection
```

默认 resnet18 便于先验证；可通过 --backbone wide_resnet50_2 对照较大骨干。ratio 控制正常 patch 特征的 coreset 采样，不表示图片采样或训练轮数。训练集只建立特征库；验证集按图像级 F1 选原始评分阈值，并在 F1 并列时优先减少正常误报。测试数据从不用于自动调阈值。自动阈值只保存到 calibrated.pt，model.pt 保留未校准版本。

评估输出 metrics.json、predictions.csv、evaluation.png：图像 AUROC、Precision、Recall、F1、误报/漏检、混淆矩阵、评分分布、各缺陷类别及生成批次表现、平均/P50/P95 推理时间。类别分组含同一组正常图。热力图采用验证集确定的统一颜色范围，避免每张图单独拉伸造成“任何图片都很红”。没有缺陷掩码就不报告像素定位准确率。

推理时间包含打开后的预处理、分块、模型、异常图重采样和设备同步，不含模型加载和硬盘读图。评估先 warm-up 一张并排除该次时间；记录设备和输入尺寸。小样本统计波动大，第一阶段只验证流程。

## 高分辨率对照

原图不变；先 256 输入，再用 512 或 1024 整图对照。可使用 512 原图块、512 模型输入进行不缩小块内细节的对照：

```sh
uv run ceramic-poc train ../datasets/ceramic_tile_phase1 runs/phase1_tiles512 --size 512 --tile-size 512 --ratio 0.01
uv run ceramic-poc calibrate runs/phase1_tiles512/model.pt ../datasets/ceramic_tile_phase1
uv run ceramic-poc evaluate runs/phase1_tiles512/calibrated.pt ../datasets/ceramic_tile_phase1 runs/phase1_tiles512_test
```

训练和推理使用相同分块，50% 重叠；重叠异常图取平均，图像评分取各块原始异常评分最大值。分块改变评分分布，因此每个模型独立使用验证集校准，不能拿整图阈值直接套分块。

## 第二阶段和真实数据对照

第一阶段流程和候选图质量通过后：

```sh
uv run ceramic-poc plan ../datasets/ceramic_tile --phase 2
uv run ceramic-poc generate ../datasets/ceramic_tile
```

计划共 260 张：160 正常训练、20 正常验证、20 正常测试；划痕、裂纹、污渍各 20 张，每类 10 验证和 10 测试。phase1 和 phase2 分开保存，防止用第一阶段测试结果调完参数再把旧测试成绩当作最终测试。不要仅因小规模合成成绩好就大量生成；先检查生成差异。

[MVTec AD 官方下载与许可](https://www.mvtec.com/research-teaching/datasets/mvtec-ad)：公开真实工业数据作为独立对照。下载并解压后：

```sh
uv run ceramic-poc mvtec-import C:/datasets/mvtec_anomaly_detection ../datasets/mvtec_tile --category tile
uv run ceramic-poc train ../datasets/mvtec_tile runs/mvtec_tile --size 256 --ratio 0.01
uv run ceramic-poc calibrate runs/mvtec_tile/model.pt ../datasets/mvtec_tile
uv run ceramic-poc evaluate runs/mvtec_tile/calibrated.pt ../datasets/mvtec_tile runs/mvtec_tile_test
```

导入器固定 seed=20261008：原正常 train 的 20% 用作正常验证，余下固定选取最多 20 张建立特征库（可用 --normal-train-limit 调整），其余不参与实验；各类原缺陷 test 的一半用于阈值校准，其余最终测试；原正常 test 全部保留最终测试。此分法和官方标准基准不同，报告不得冒充官方基准成绩。原始图片 ID、数据来源和固定划分记录在 CSV。缺陷类别不参与建库。

## 最小检查

```sh
uv run python tests/check_poc.py
```

检查使用明确标识的程序化测试夹具，仅检验代码流程，不伪装成 AI 生图或真实工业评估。包含计划数量和来源分组、导入校验、防泄漏、预训练 PatchCore 建库/保存/加载、验证集校准、异常图、最终测试指标、分块覆盖和 Gradio 构建。

参考：

- [Anomalib PatchCore 官方文档](https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html)
- [Anomalib 2.6.2 发布包](https://pypi.org/project/anomalib/2.6.2/)
- [PatchCore 论文](https://openaccess.thecvf.com/content/CVPR2022/html/Roth_Towards_Total_Recall_in_Industrial_Anomaly_Detection_CVPR_2022_paper.html)

## 本机已运行的实验（2026-10-08）

- 30 张第一阶段 AI 候选图已生成，独立 PNG 与完整提示词、来源、尺寸处理和质量检查记录位于 ../datasets/ceramic_tile_phase1。
- 12 张正常图建库；验证 4 正常＋6 缺陷；最终测试 4 正常＋4 缺陷。256、512 整图和 512 分块均在这 8 张测试图上全对，样本不足以支持泛化准确率结论。
- CPU 平均推理：256 整图约 22 ms；512 整图约 77 ms；512 分块约 714 ms。分块为了控制内存，采样比例为 0.001，整图为 0.01；对照同时改变了采样比例，不能把差异只归因于分辨率。
- 官方 MVTec AD 全包校验 SHA256 后，仅提取 tile。20 张真实正常图建库，验证 46 正常＋41 缺陷，测试 33 正常＋43 缺陷。AUROC 0.94996，Precision 0.97368，Recall 0.86047，F1 0.91358，误报率 0.03030，漏检率 0.13953，CPU 平均约 20 ms。
- 真实测试混淆矩阵：正常 32 对、1 误报；缺陷 37 检出、6 漏检。灰色划痕和粗糙表面各漏 3 张；没有根据这些测试结果修改阈值。
- 以上为自定义冻结划分，不是官方标准基准，也未验证 Windows/RTX 3080 或像素定位准确率。

每次实验的完整结果在 runs/*_test/metrics.json、predictions.csv 和 evaluation.png；汇总为 experiment-results.json。

## 微弱缺陷（按用户补充要求更新）

新的生成计划默认 --difficulty subtle；--difficulty standard 保留明显缺陷对照。既有第一阶段图片不删除、不伪装成微弱缺陷。完整批次已改成微弱提示词，提示词冻结保存在 plan.json。

微弱版本：短浅划痕约 0.5–1 像素宽、长度约瓷砖宽度 1–3%；短发丝裂纹约 0.5–1 像素宽、长度 2–5%；浅色小污渍直径约瓷砖宽度 0.5–1.5%。这些是生成意图，不是人工测量的缺陷尺寸。放大后应有可观察缺陷，不能把完全看不见的变化硬标成缺陷。

已用现有系统生成各一张微弱预览，位于 ../datasets/ceramic_tile_subtle_preview。沿用第一阶段 512 整图模型和冻结阈值 14.63647，划痕得分 16.57441、裂纹 14.81339，均检出；浅污渍得分 11.90099，漏检。512 分块模型也检出前两张、漏掉污渍。三张原正常底图均判定正常。未根据预览修改阈值，这三张只能作为难度预览，不能当作准确率评估。完整分数和叠加图保存在 runs/subtle_preview。

批量生成期间可以创建数据集目录下的 pause-after-current 空文件，当前请求保存完成后会在下一次请求前暂停。继续前移除该文件，再运行 generate。不要强行中断在途请求；本次修改提示词时一个在途正常图请求的响应未确认，已保留 retired-requests.json，未自动重发该请求，使用独立替代图补足数量。

## 多厂家、多包装参考库

网页顶部选择包装，数据目录、模型及模型内的校准阈值随包装切换。切换时清空检测结果并关闭手动阈值；检测结果显示包装名称、适用厂家和实际模型路径。选择已登记包装时，检测及测试使用保存的绑定，不受临时修改模型路径影响；选择“临时实验”可沿用原手动流程。

新包装：在数据集页导入 PNG 和 metadata.csv，填写其目录；在包装参考库页填写名称/规格、适用厂家、颜色/尺寸/印刷/拍摄条件。模型路径留空时可先登记数据，随后到训练页指定一个未使用的输出目录建立正常特征库并校准，成功后自动绑定该包装。已有 calibrated.pt 可在登记时绑定，系统检查其数据目录对应关系及有限校准阈值。未建库包装不能检测，模型与包装数据不匹配会被拒绝。名字须唯一，新版本可登记不同名字，保留旧记录。

记录持久化到 ceramic_poc/runs/packaging-profiles.json，图片和权重按各自路径保存，不复制大文件。备份需同时保存 JSON、对应数据目录和模型目录；迁移到 Windows 后需按新本地路径重新登记。当前是单进程本地参考库管理，不自动识别厂家或包装，不自动裁剪对齐，也不提供缺陷类型分类。瓷砖示例不能作为火腿肠包装模型使用；真实新包装仍需正常样本及独立验证、测试数据。

## 第二阶段生成恢复记录

完成 165 张后 good_0166 请求收到 HTTP 500：上游流 INTERNAL_ERROR，未返回图片。失败请求保留为 RETIRED_UNKNOWN，独立 good_0166_replacement 补位；相关缺陷来源指向替代图，划分不变。随后服务模型列表不再包含 gpt-image-2.5，剩余请求明确选择当前提供的 gpt-image-2.5-flare。此批次生成条件发生变化，不能称为同一模型生成；逐图 requested_model 保存在 receipts.json，真实返回模型仍以 actual_model 为准。

命令行支持 generate --model 指定服务实际提供的名称，不会静默切换模型。失败记录保留错误类型和 HTTP 状态，不保存密钥。恢复流水线日志为 ceramic_poc/phase2-pipeline.log，全部图片完成后才校验、建库、校准和测试。

完成 253 张后，本机代理停止，stain_0014 收到 RemoteProtocolError（未返回响应）。重启同一本机代理后，将该请求保留为 RETIRED_UNKNOWN，使用 stain_0014_replacement 补位，仍引用原正常底图、保持原测试集划分与微弱污渍提示词。

第二阶段现已完成：260 张独立保存的 1024 PNG（200 正常＋划痕/裂纹/污渍各 20），无完全相同的解码像素。160 正常建库、20 正常＋30 缺陷校准、20 正常＋30 缺陷最终测试。256 整图、ratio=0.01、CPU：AUROC 0.98333、Precision 0.96552、Recall 0.93333、F1 0.94915，正常 19 对/1 误报，缺陷 28 检出/2 漏检（均为划痕）；平均约 25.1 ms。阈值 6.83043 来自验证集，未按最终测试修改。

模型 runs/phase2_256/calibrated.pt，报告 runs/phase2_256_test/metrics.json，已登记“瓷砖演示 · 260 张微弱缺陷批次”参考库。200 正常与 60 缺陷缩略图已审阅；低分辨率近重复检查有 26 对候选，仍保留供进一步人工复核，不宣称已排除所有近重复。生成模型名称中途变化、编辑可能改变缺陷以外区域，因此结果仅说明合成数据流程可运行，不能替代真实火腿肠包装验证或像素级定位评估。
