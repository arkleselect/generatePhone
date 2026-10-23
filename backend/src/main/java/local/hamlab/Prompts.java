package local.hamlab;

import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.IntStream;
import static local.hamlab.Models.*;

/** Validates business parameters once and expands maintainable stage-specific templates. */
@Service
public class Prompts {
    private static final List<String> INK_LOCATIONS = List.of(
        "日期左侧、靠近左端的红色肠衣空白处，与日期完全分离",
        "产品中段的红色肠衣表面、日期正上方，与字符留出空隙",
        "日期右侧的红色肠衣空白处，与日期完全分离",
        "产品中段的红色肠衣表面、日期正下方，与字符留出空隙");
    public static final Set<String> TYPES = DefectCatalog.ALL.keySet();
    public static final Set<String> POSITION_TYPES = DefectCatalog.positionTypes();
    public static final Set<String> SEVERITY_TYPES = DefectCatalog.severityTypes();
    private final String common = template("common"), pose = template("pose"), defect = template("defect");
    private static String template(String name) {
        try (var stream = new ClassPathResource("prompts/" + name + ".txt").getInputStream()) {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        } catch (Exception e) { throw new IllegalStateException("提示词模板读取失败", e); }
    }
    public static void require(boolean condition, String message) {
        if (!condition) throw new IllegalArgumentException(message);
    }
    public static void date(String value) {
        require(value != null && value.matches("[0-9A-Za-z./-]{1,32}"), "日期应为1至32位数字、字母或 ./- 字符");
    }
    public List<Map<String, Object>> mapping(String value) {
        date(value);
        return IntStream.range(0, value.length()).mapToObj(i -> Map.<String, Object>of("position", i + 1, "character", value.substring(i, i + 1))).toList();
    }
    public static void roi(Roi r) {
        require(r != null && Double.isFinite(r.x()+r.y()+r.width()+r.height()) && r.x() >= 0 && r.y() >= 0 &&
            r.width() > 0 && r.height() > 0 && r.x()+r.width() <= 1.000001 && r.y()+r.height() <= 1.000001, "请框选有效的日期编辑区域");
    }
    public static void pose(Pose p) {
        require(p != null && Set.of("original","center","left","right","up","down","rotate","diagonal","vertical","custom").contains(p.kind()), "姿势类型无效");
        require(Double.isFinite(p.angle()) && Math.abs(p.angle()) <= 180 && Double.isFinite(p.shift()) && p.shift() >= 0 && p.shift() <= 25, "角度应在±180度内，位移应在0至25%内");
        require(p.description() != null && p.description().length() <= 1000, "姿势说明过长");
        require(!"custom".equals(p.kind()) || !p.description().isBlank(), "请填写自定义姿势");
    }
    public static void defect(Defect d, String date) {
        require(d != null && TYPES.contains(d.type()), "缺陷类型无效");
        require(d.positions() != null && d.positions().stream().allMatch(i -> i != null && i >= 1 && i <= date.length()), "字符位置超出日期长度");
        require(d.positions().size() == new HashSet<>(d.positions()).size(), "字符位置不能重复");
        require(!POSITION_TYPES.contains(d.type()) || !d.positions().isEmpty(), "请选择受影响字符");
        require(!SEVERITY_TYPES.contains(d.type()) || Set.of("轻度","中度","重度").contains(Objects.toString(d.severity(),"")), "请选择有效缺陷程度");
        require(d.description() != null && d.description().length() <= 1000 && d.object() != null && d.object().length() <= 200, "说明过长或缺失");
        require(!"custom".equals(d.type()) || !d.description().isBlank(), "请填写自定义缺陷名称和说明");
        require(!"occlusion".equals(d.type()) || !d.object().isBlank(), "请填写遮挡物");
        require(!"partial_break".equals(d.type()) || Set.of("上部","下部","左侧","右侧","局部笔画").contains(Objects.toString(d.part(),"")), "请选择断码部位");
        require(!Set.of("smear","double_print","ink_transfer").contains(d.type()) || Set.of("左","右","上","下").contains(Objects.toString(d.direction(),"")), "请选择方向");
    }
    public String build(String stage, Params p) {
        return build(stage,p,false);
    }
    public String build(String stage, Params p, boolean defectReference) {
        return build(stage,p,defectReference,0);
    }
    public String build(String stage, Params p, boolean defectReference, int inkLocationIndex) {
        date(p.baseDate()); pose(p.pose());
        String map = IntStream.range(0,p.baseDate().length()).mapToObj(i -> "第"+(i+1)+"位："+p.baseDate().charAt(i)).reduce((a,b)->a+"；"+b).orElse("");
        String body;
        if ("POSE".equals(stage)) body = pose.replace("{{effect}}", poseEffect(p.pose()));
        else {
            defect(p.defect(), p.baseDate()); roi(p.roi());
            boolean inkTransfer="ink_transfer".equals(p.defect().type());
            body = defect.replace("{{effect}}", defectEffect(p.defect(),p.baseDate(),inkLocationIndex))
                .replace("{{roi}}",p.roi().toString())
                .replace("{{edit_scope}}",inkTransfer
                    ? "只编辑日期和本张指定位置的一小处红色肠衣表面；印染位置可以在日期编辑区域之外。"
                    : "只编辑日期及实现本次缺陷所必需的紧邻区域。");
        }
        if(defectReference) require("DEFECT".equals(stage),"缺陷参考图只用于阶段B");
        String referenceInstruction = defectReference
            ? "参考图已有人为确认的同类缺陷：保留其真实的墨迹质感与局部形态作为参考，但改变缺陷的具体位置、长度、深浅和细节；本次以任务参数为准，不直接复制整张图。"
            : "不要照搬参考图已有的缺失位置、断码形状、浅淡分布或遮挡方式。本次以任务参数为准。";
        return common.replace("{{reference_instruction}}",referenceInstruction).replace("{{date}}",p.baseDate()).replace("{{mapping}}",map)
            + body.replace("{{defect_reference_instruction}}",defectReference
                ? "参考原有同类缺陷的形态，重新生成一处主要缺陷，不叠加原有痕迹"
                : "不要继承参考图的旧缺陷，只实现一种主要效果");
    }
    private String poseEffect(Pose p) {
        String effect = switch (p.kind()) {
            case "original" -> "保持原姿势"; case "center" -> "横放居中";
            case "left" -> "向左移动画面宽度的"+p.shift()+"%"; case "right" -> "向右移动画面宽度的"+p.shift()+"%";
            case "up" -> "向上移动画面高度的"+p.shift()+"%"; case "down" -> "向下移动画面高度的"+p.shift()+"%";
            case "rotate", "diagonal" -> "旋转"+p.angle()+"度（正数顺时针，负数逆时针）";
            case "vertical" -> "竖向摆放"; default -> p.description();
        };
        return effect + "。补充：" + p.description();
    }
    private String defectEffect(Defect d, String date, int inkLocationIndex) {
        String positions = d.positions().stream().sorted().map(i -> "第"+i+"位「"+date.charAt(i-1)+"」").reduce((a,b)->a+"、"+b).orElse("全部字符");
        String effect = DefectCatalog.ALL.get(d.type()).effect()
            .replace("{positions}",positions).replace("{part}",Objects.toString(d.part(),""))
            .replace("{direction}",Objects.toString(d.direction(),""))
            .replace("{location}",INK_LOCATIONS.get(Math.floorMod(inkLocationIndex,INK_LOCATIONS.size())))
            .replace("{object}",Objects.toString(d.object(),""))
            .replace("{description}",Objects.toString(d.description(),""));
        return effect + (SEVERITY_TYPES.contains(d.type()) ? "。程度："+d.severity() : "") + "。补充："+d.description();
    }
}
