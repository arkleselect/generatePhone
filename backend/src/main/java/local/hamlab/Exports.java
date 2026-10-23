package local.hamlab;

import org.springframework.stereotype.Service;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.zip.*;
import static local.hamlab.Models.*;

/** Export only explicit metadata, preserving provenance and distinguishing intended from verified labels. */
@Service
public class Exports {
    private final Store store; private final Images images;
    public Exports(Store store,Images images) { this.store=store; this.images=images; }
    public List<Asset> select(String pose,String defect,String review) {
        Prompts.require(Set.of("APPROVED","PENDING","REJECTED","ALL").contains(review),"导出审核筛选无效");
        return store.assets().stream().filter(a -> a.role().equals("RESULT") && !a.sourceType().equals("TEST"))
            .filter(a -> review.equals("ALL") || a.review().equals(review))
            .filter(a -> pose.isBlank() || pose.equals(a.parentPoseId()))
            .filter(a -> defect.isBlank() || defect.equals(store.task(a.taskId()).params().defect().type())).toList();
    }
    public void zip(OutputStream output,List<Asset> selected) throws IOException {
        try(ZipOutputStream zip=new ZipOutputStream(output,StandardCharsets.UTF_8)) {
            StringBuilder manifest=new StringBuilder(); Map<String,Object> configs=new LinkedHashMap<>();
            for(Asset a:selected) {
                Task task=store.task(a.taskId()); String name="images/"+a.filename();
                zip.putNextEntry(new ZipEntry(name)); Files.copy(images.file(a,false),zip); zip.closeEntry();
                Map<String,Object> m=new LinkedHashMap<>();
                m.put("image_id",a.id());m.put("root_source_id",a.rootSourceId());m.put("parent_pose_id",a.parentPoseId());
                m.put("source_type",a.sourceType());m.put("synthetic",a.sourceType().equals("AI"));m.put("base_date",a.baseDate());
                m.put("pose",a.pose());m.put("expected_defect",task.params().defect());m.put("human_label",a.label());m.put("quality",a.quality());
                m.put("review",a.review());m.put("rejection_reason",a.rejectionReason());m.put("prompt",task.prompt());m.put("settings",task.settings());
                // Casing and shape defects have no date edit region, so edit_roi may be null.
                Map<String,Object> generation=new LinkedHashMap<>();
                generation.put("image_id",task.inputId());generation.put("edit_roi",task.params().roi());generation.put("task_id",task.id());generation.put("parameters_are_prompt_preferences",true);
                m.put("generation_parameters",generation);
                m.put("actual_model",task.actualModel());m.put("execution_channel",task.executionChannel());
                m.put("provider_request_id",task.providerRequestId());m.put("filename",name);m.put("width",a.width());m.put("height",a.height());
                m.put("created_at",a.createdAt());m.put("spatial_annotation",a.annotations().isEmpty()?null:a.annotations());
                manifest.append(store.json().write(m)).append('\n'); configs.put(task.batchId(),store.tasks(task.batchId()));
            }
            entry(zip,"manifest.jsonl",manifest.toString()); entry(zip,"generation-config.json",store.json().write(configs));
            entry(zip,"README.txt","AI合成数据，不是真实产线测试照片。预期缺陷与人工标签独立。ROI仅为编辑区域，不是缺陷标注。请按root_source_id分组划分数据集。测试模式图片永不导出。\n");
        }
    }
    public void detectionZip(OutputStream output,List<Asset> selected) throws IOException {
        var classes=selected.stream().flatMap(a->a.annotations().stream()).map(Annotation::classId).distinct().sorted().toList();
        try(ZipOutputStream zip=new ZipOutputStream(output,StandardCharsets.UTF_8)) {
            for(Asset asset:selected) {
                zip.putNextEntry(new ZipEntry("images/"+asset.filename()));
                Files.copy(images.file(asset,false),zip);zip.closeEntry();
                StringBuilder labels=new StringBuilder();
                for(Annotation a:asset.annotations()) {
                    Roi b=a.box();
                    labels.append(classes.indexOf(a.classId())).append(' ')
                        .append(b.x()+b.width()/2).append(' ').append(b.y()+b.height()/2).append(' ')
                        .append(b.width()).append(' ').append(b.height()).append('\n');
                }
                entry(zip,"labels/"+asset.id()+".txt",labels.toString());
            }
            entry(zip,"classes.txt",String.join("\n",classes)+"\n");
            entry(zip,"README.txt","YOLO检测框：class_id x_center y_center width height，坐标归一化。仅含已审核、人工框选的缺陷图。训练前请按原始图片来源划分train/val，并补充无缺陷图；此包没有独立验证集。\n");
        }
    }
    private void entry(ZipOutputStream zip,String name,String text) throws IOException {
        zip.putNextEntry(new ZipEntry(name));zip.write(text.getBytes(StandardCharsets.UTF_8));zip.closeEntry();
    }
}
