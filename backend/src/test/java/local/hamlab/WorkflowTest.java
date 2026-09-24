package local.hamlab;

import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.zip.ZipInputStream;
import static org.assertj.core.api.Assertions.*;
import static local.hamlab.Models.*;

/** Exercises persisted workflows without spending credits or substituting test images for AI results. */
@SpringBootTest
@ActiveProfiles("test")
class WorkflowTest {
    @Autowired Store store;
    @Autowired Images images;
    @Autowired Prompts prompts;
    @Autowired Batches batches;
    @Autowired QueueWorker worker;
    @Autowired Exports exports;
    @Autowired AccountTasks account;
    @Autowired ProviderConfig config;
    @Autowired DatasetPlans plans;
    private static final String DATE="20310927";
    private final Pose pose=new Pose("original",0,5,"");
    private final Roi roi=new Roi(.2,.3,.5,.2);
    @BeforeEach void clear() { store.jdbc().update("DELETE FROM image_task");store.jdbc().update("DELETE FROM batch");store.jdbc().update("DELETE FROM asset"); }
    private byte[] png() throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();ImageIO.write(new BufferedImage(200,100,BufferedImage.TYPE_INT_RGB),"png",out);return out.toByteArray();
    }
    private Asset base() throws IOException {
        Asset a=images.upload(png(),"POSE",DATE);images.region(a.id(),roi);
        return images.review(a.id(),new Review("APPROVED","normal","OK",""));
    }
    private Defect missing(Integer... positions) { return new Defect("missing_chars",List.of(positions),"","上部","右","",""); }
    private String draft(List<String> inputs,List<Defect> defects,int count) {
        return ((Map<?,?>)batches.draft(new Draft("DEFECT","TEST",inputs,DATE,List.of(),defects,count)).get("batch")).get("id").toString();
    }
    private void confirm(String id) { batches.confirm(id,new Confirm(true,store.tasks(id).stream().map(t->new PromptEdit(t.id(),t.prompt())).toList())); }
    /** Deletion removes unreferenced source files while preserving task and lineage inputs. */
    @Test void sourceDeletionPreservesReferencedAssets() throws Exception {
        Asset unused=images.upload(png(),"SOURCE",DATE);
        images.deleteSource(unused.id());
        assertThatThrownBy(()->store.asset(unused.id())).isInstanceOf(IllegalArgumentException.class);
        assertThat(images.file(unused,false)).doesNotExist();
        assertThat(images.file(unused,true)).doesNotExist();
        assertThatThrownBy(()->images.deleteSource(unused.id())).hasMessageContaining("不存在");
        Asset used=images.upload(png(),"SOURCE",DATE);
        batches.draft(new Draft("POSE","TEST",List.of(used.id()),DATE,List.of(pose),List.of(),1));
        assertThatThrownBy(()->images.deleteSource(used.id())).hasMessageContaining("引用");
        assertThat(images.file(used,false)).exists();
        assertThat(images.file(used,true)).exists();
        Asset child=base(), parent=images.upload(png(),"SOURCE",DATE);
        store.jdbc().update("UPDATE asset SET root_source_id=? WHERE id=?",parent.id(),child.id());
        assertThatThrownBy(()->images.deleteSource(parent.id())).hasMessageContaining("引用");
        assertThat(store.asset(parent.id())).isNotNull();
        assertThatThrownBy(()->images.deleteSource(child.id())).hasMessageContaining("仅支持");
    }
    /** Exhaustive coverage includes repeated digits at distinct positions and date-major ordering. */
    @Test void exhaustiveDatasetCoverageAndLimits() throws Exception {
        Asset input=base();
        Randomization random=new Randomization("FIXED","2027-12-20","2027-12-31","yyyyMMdd",8);
        Draft request=new Draft("DEFECT","TEST",List.of(input.id()),"20260923",List.of(),List.of(missing()),1,random,new Coverage("ALL",7));
        String id=((Map<?,?>)batches.draft(request).get("batch")).get("id").toString();
        List<Task> tasks=store.tasks(id);
        assertThat(tasks).hasSize(2040);
        assertThat(tasks.subList(0,255)).allMatch(t->t.params().baseDate().equals("20260923"));
        assertThat(tasks.subList(0,255).stream().map(t->t.params().defect().positions()).distinct()).hasSize(255);
        assertThat(tasks.stream().map(t->t.params().baseDate()).distinct()).hasSize(8);
        assertThat(tasks.getFirst().params().defect().positions()).containsExactly(1);
        assertThat(plans.positions("2026-09-23","CONTIGUOUS",1)).hasSize(36).allMatch(p->!p.contains(5) && !p.contains(8));
        assertThat(plans.positions("20260923","ALL",2)).hasSize(247);
        assertThatThrownBy(()->plans.expand(new Draft("DEFECT","TEST",List.of(input.id()),"20260923",List.of(),List.of(missing()),20,random,new Coverage("ALL",0)))).hasMessageContaining("5000");
        assertThatThrownBy(()->plans.expand(new Draft("DEFECT","TEST",List.of(input.id()),"20271220",List.of(),List.of(missing()),1,random,new Coverage("ALL",12)))).hasMessageContaining("不重复日期");
    }
    /** A referenced member rolls back prior deletes and never removes their on-disk bytes. */
    @Test void bulkDeleteIsAtomicAndSupportsUnusedPoses() throws Exception {
        Asset source=images.upload(png(),"SOURCE",DATE), poseAsset=base();
        images.deleteAssets(List.of(source.id(),poseAsset.id()));
        assertThat(images.file(source,false)).doesNotExist();
        assertThat(images.file(poseAsset,false)).doesNotExist();
        Asset a=images.upload(png(),"SOURCE",DATE), b=images.upload(png(),"SOURCE",DATE);
        Asset first=a.id().compareTo(b.id())<0?a:b, used=first==a?b:a;
        batches.draft(new Draft("POSE","TEST",List.of(used.id()),DATE,List.of(pose),List.of(),1));
        assertThatThrownBy(()->images.deleteAssets(List.of(first.id(),used.id()))).hasMessageContaining("引用");
        assertThat(store.asset(first.id())).isNotNull();
        assertThat(images.file(first,false)).exists();
        assertThat(images.file(first,true)).exists();
    }
    /** Newly configured industrial classes generate prompts without changing historical task ids. */
    @Test void sharedCatalogAndUnknownManualRecovery() throws Exception {
        assertThat(Prompts.TYPES).contains("blur","stain","misalignment","normal","no_print");
        for(String type:Prompts.TYPES) {
            Defect defect=new Defect(type,Prompts.POSITION_TYPES.contains(type)?List.of(1,2):List.of(),
                Prompts.SEVERITY_TYPES.contains(type)?"中度":"","上部","右","灰色碎屑","局部自然变化");
            assertThat(prompts.build("DEFECT",new Params(DATE,pose,defect,roi))).doesNotContain("{positions}","{direction}","{description}");
        }
        Asset input=base();
        String id=((Map<?,?>)batches.draft(new Draft("DEFECT","ACCOUNT",List.of(input.id()),DATE,List.of(),List.of(missing(1)),1)).get("batch")).get("id").toString();
        confirm(id);worker.tick();Task task=store.tasks(id).getFirst();
        account.fail(task.id(),"提交后未确认生成结果",true);
        assertThatThrownBy(()->account.complete(task.id(),png(),"","BROWSER_CHATGPT")).isInstanceOf(IllegalArgumentException.class);
        Asset recovered=account.complete(task.id(),png(),"","MANUAL_CHATGPT");
        assertThat(store.task(task.id()).status()).isEqualTo("SUCCEEDED");
        assertThat(recovered.review()).isEqualTo("PENDING");
        assertThatThrownBy(()->account.complete(task.id(),png(),"","MANUAL_CHATGPT")).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void datePositionsAndMissingTemplatesAreDynamic() {
        assertThat(prompts.mapping(DATE).get(5)).containsEntry("position",6).containsEntry("character","9");
        String first=prompts.build("DEFECT",new Params(DATE,pose,missing(1),roi));
        String pair=prompts.build("DEFECT",new Params(DATE,pose,missing(5,6),roi));
        String tail=prompts.build("DEFECT",new Params(DATE,pose,missing(5,6,7,8),roi));
        assertThat(first).contains("第1位「2」完全缺失","其他字符保持原位").doesNotContain("20260923");
        assertThat(pair).contains("第5位「0」、第6位「9」完全缺失");
        assertThat(tail).contains("第5位「0」、第6位「9」、第7位「2」、第8位「7」完全缺失","绝不能前移");
        assertThatThrownBy(()->prompts.build("DEFECT",new Params("123",pose,missing(5),roi))).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void batchExpansionKeepsEveryInputFixedAndRequiresConfirmation() throws Exception {
        Asset a=base(), b=base(); String id=draft(List.of(a.id(),b.id()),List.of(missing(1),missing(5,6)),3);
        assertThat(store.tasks(id)).hasSize(12).allMatch(t->t.status().equals("DRAFT"));
        worker.tick(); assertThat(store.tasks(id)).allMatch(t->t.attempts()==0);
        confirm(id);worker.tick();worker.tick();
        assertThat(store.tasks(id).stream().filter(t->t.status().equals("SUCCEEDED"))).hasSize(2);
        assertThat(store.tasks(id)).allMatch(t->Set.of(a.id(),b.id()).contains(t.inputId()));
        assertThatThrownBy(()->confirm(id)).isInstanceOf(IllegalArgumentException.class);
        Asset result=store.assets().stream().filter(x->x.role().equals("RESULT")).findFirst().orElseThrow();
        assertThatThrownBy(()->draft(List.of(result.id()),List.of(missing(1)),1)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void pauseCancelRetryAndRecoveryDoNotResubmitSuccess() throws Exception {
        String id=draft(List.of(base().id()),List.of(missing(1)),3);confirm(id);worker.tick();
        Task success=store.tasks(id).stream().filter(t->t.status().equals("SUCCEEDED")).findFirst().orElseThrow();
        batches.action(id,"pause");worker.tick();assertThat(store.tasks(id).stream().filter(t->t.status().equals("SUCCEEDED"))).hasSize(1);
        Task failed=store.tasks(id).stream().filter(t->t.status().equals("PENDING")).findFirst().orElseThrow();
        store.jdbc().update("UPDATE image_task SET status='FAILED',attempts=1 WHERE id=?",failed.id());
        batches.action(id,"retry");worker.tick();
        assertThat(store.task(success.id()).outputId()).isEqualTo(success.outputId());assertThat(store.task(success.id()).attempts()).isEqualTo(1);
        store.jdbc().update("UPDATE image_task SET status='RUNNING' WHERE status='PENDING'");worker.recover();
        assertThat(store.tasks(id)).anyMatch(t->t.status().equals("UNKNOWN"));
        assertThatThrownBy(()->batches.action(id,"retry")).isInstanceOf(IllegalArgumentException.class);
        Task unknown=store.tasks(id).stream().filter(t->t.status().equals("UNKNOWN")).findFirst().orElseThrow();
        assertThatThrownBy(()->batches.resolveUnknown(unknown.id(),false)).isInstanceOf(IllegalArgumentException.class);
        batches.resolveUnknown(unknown.id(),true);batches.action(id,"retry");batches.action(id,"cancel");worker.tick();
        assertThat(store.task(unknown.id()).status()).isEqualTo("CANCELLED");
        assertThat(store.task(success.id()).status()).isEqualTo("SUCCEEDED");
    }
    @Test void deleteBatchPreservesInputsAndProtectsLiveOrGeneratedTasks() throws Exception {
        Asset input=base();
        String draftId=draft(List.of(input.id()),List.of(missing(1)),1);
        batches.delete(draftId);
        assertThat(store.assets()).extracting(Asset::id).contains(input.id());
        assertThatThrownBy(()->store.batch(draftId)).hasMessageContaining("不存在");
        String id=draft(List.of(input.id()),List.of(missing(1)),1);
        confirm(id);
        assertThatThrownBy(()->batches.delete(id)).hasMessageContaining("暂停");
        batches.action(id,"pause");
        for(String state:List.of("RUNNING","AWAITING_IMAGE","UNKNOWN")) {
            store.jdbc().update("UPDATE image_task SET status=? WHERE batch_id=?",state,id);
            assertThatThrownBy(()->batches.delete(id)).hasMessageContaining("待核实");
            assertThat(store.tasks(id)).hasSize(1);
        }
        store.jdbc().update("UPDATE image_task SET status='SUCCEEDED',output_id=? WHERE batch_id=?",input.id(),id);
        assertThatThrownBy(()->batches.delete(id)).hasMessageContaining("生成图片");
        store.jdbc().update("UPDATE image_task SET status='FAILED',output_id=NULL WHERE batch_id=?",id);
        batches.delete(id);
        assertThat(store.tasks(id)).isEmpty();
        assertThat(images.file(store.asset(input.id()),false)).exists();
    }
    @Test void accountQueuePreservesInputAndImportsExactlyOnce() throws Exception {
        Asset a=base();
        String id=((Map<?,?>)batches.draft(new Draft("DEFECT","ACCOUNT",List.of(a.id()),DATE,List.of(),List.of(missing(1)),2)).get("batch")).get("id").toString();
        confirm(id);worker.tick();
        Task first=store.tasks(id).stream().filter(t->t.status().equals("AWAITING_IMAGE")).findFirst().orElseThrow();
        assertThat(account.next()).containsEntry("available",true);
        worker.tick(); assertThat(store.tasks(id).stream().filter(t->t.status().equals("AWAITING_IMAGE"))).hasSize(1);
        worker.recover(); assertThat(store.task(first.id()).status()).isEqualTo("AWAITING_IMAGE");
        Asset result=account.complete(first.id(),png(),"","CLIPROXY_CODEX");
        assertThat(result.parentPoseId()).isEqualTo(a.id());assertThat(result.sourceType()).isEqualTo("AI");
        assertThat(result.review()).isEqualTo("PENDING");assertThat(store.task(first.id()).actualModel()).isNull();
        assertThat(store.task(first.id()).executionChannel()).isEqualTo("CLIPROXY_CODEX");
        assertThatThrownBy(()->account.complete(first.id(),png(),"","MANUAL_CHATGPT")).isInstanceOf(IllegalArgumentException.class);
        worker.tick(); Task second=(Task)account.next().get("task"); assertThat(second.inputId()).isEqualTo(a.id());
        assertThat(second.id()).isNotEqualTo(first.id());
        BufferedImage mask=ImageIO.read(new ByteArrayInputStream(images.mask(a,roi)));
        assertThat(mask.getRGB(50,35)>>>24).isZero();assertThat(mask.getRGB(0,0)>>>24).isEqualTo(255);
        ByteArrayOutputStream bundle=new ByteArrayOutputStream();account.bundle(first.id(),bundle);assertThat(bundle.size()).isPositive();
    }
    @Test void exportDefaultsExcludePendingRejectedAndTestImagesAndKeepHumanLabels() throws Exception {
        Asset a=base();String id=draft(List.of(a.id()),List.of(missing(1)),3);confirm(id);worker.tick();worker.tick();worker.tick();
        List<Asset> results=store.assets().stream().filter(x->x.role().equals("RESULT")).toList();
        for(Asset result:results) store.jdbc().update("UPDATE asset SET source_type='AI' WHERE id=?",result.id()); // Fixture only, no production path can change provenance.
        images.review(results.get(0).id(),new Review("APPROVED","missing_chars","NG","核对首位缺失"));
        images.review(results.get(1).id(),new Review("REJECTED","","","字符移位"));
        List<Asset> selected=exports.select("","","APPROVED");assertThat(selected).hasSize(1);
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();exports.zip(bytes,selected);
        Map<String,String> entries=new HashMap<>();
        try(ZipInputStream zip=new ZipInputStream(new ByteArrayInputStream(bytes.toByteArray()))) {
            for(var entry=zip.getNextEntry();entry!=null;entry=zip.getNextEntry()) if(!entry.getName().startsWith("images/")) entries.put(entry.getName(),new String(zip.readAllBytes(),StandardCharsets.UTF_8));
        }
        assertThat(entries.get("manifest.jsonl")).contains("\"quality\":\"NG\"","\"root_source_id\":\""+a.rootSourceId(),"\"spatial_annotation\":null");
        assertThat(entries.toString()).doesNotContain("apiKey","Authorization","OPENAI_API_KEY");
        store.jdbc().update("UPDATE asset SET source_type='TEST' WHERE id=?",results.get(0).id());
        assertThat(exports.select("","","APPROVED")).isEmpty();
    }
    @Test void poseStageKeepsRootAndRequiresFreshRegionBeforeDefects() throws Exception {
        Asset source=images.upload(png(),"SOURCE",DATE);
        String id=((Map<?,?>)batches.draft(new Draft("POSE","TEST",List.of(source.id()),DATE,
            List.of(new Pose("rotate",-12,5,"")),List.of(),1)).get("batch")).get("id").toString();
        Task task=store.tasks(id).getFirst();
        assertThat(task.prompt()).contains("旋转-12.0度","完整日期："+DATE).doesNotContain("固定当前底图");
        confirm(id);worker.tick();Asset poseImage=store.asset(store.task(task.id()).outputId());
        assertThat(poseImage.role()).isEqualTo("POSE");assertThat(poseImage.rootSourceId()).isEqualTo(source.id());
        assertThat(poseImage.roi()).isNull();assertThat(poseImage.review()).isEqualTo("PENDING");
        images.review(poseImage.id(),new Review("APPROVED","normal","OK",""));
        assertThatThrownBy(()->draft(List.of(poseImage.id()),List.of(missing(1)),1)).isInstanceOf(IllegalArgumentException.class);
        images.region(poseImage.id(),roi);
        String defects=draft(List.of(poseImage.id()),List.of(missing(1)),1);confirm(defects);
        Task failed=store.tasks(defects).getFirst();store.jdbc().update("UPDATE image_task SET status='FAILED',attempts=3 WHERE id=?",failed.id());
        assertThatThrownBy(()->batches.action(defects,"retry")).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void randomDatesAndDamageAreResolvedPerImageAndFrozenForRegeneration() throws Exception {
        Asset input=base();
        Randomization sampling=new Randomization("RANDOM","2024-02-28","2024-03-01","yyyy-MM-dd",4);
        Defect multi=new Defect("multi_break",List.of(),"随机","随机","随机","随机","");
        String id=((Map<?,?>)batches.draft(new Draft("DEFECT","TEST",List.of(input.id()),null,List.of(),List.of(missing(1),multi),40,sampling)).get("batch")).get("id").toString();
        List<Task> tasks=store.tasks(id);assertThat(tasks).hasSize(80);
        for(Task task:tasks) {
            Params p=task.params();
            assertThat(p.baseDate()).isIn("2024-02-28","2024-02-29","2024-03-01");
            assertThat(p.randomization()).isEqualTo(sampling);
            assertThat(task.inputId()).isEqualTo(input.id());
            assertThat(p.defect().positions()).hasSizeBetween(p.defect().type().equals("multi_break")?2:1,4);
            assertThat(p.defect().positions()).doesNotContain(5,8); // Separators are never treated as digit defects.
            assertThat(task.prompt()).contains("完整日期："+p.baseDate(),"旧日期完整替换");
            assertThat(p.defect().severity()).isNotEqualTo("随机");
        }
        Task original=tasks.getFirst();
        String clone=((Map<?,?>)batches.regenerate(original.id()).get("batch")).get("id").toString();
        assertThat(store.tasks(clone).getFirst().params()).isEqualTo(original.params());
        assertThat(store.tasks(clone).getFirst().prompt()).isEqualTo(original.prompt());
        assertThatThrownBy(()->batches.draft(new Draft("DEFECT","TEST",List.of(input.id()),null,List.of(),List.of(missing(1)),1,
            new Randomization("RANDOM","2025-02-01","2025-01-01","yyyyMMdd",4)))).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void fixedDateCanAlsoReplaceTheReferenceDateWithoutManualCharacterSelection() throws Exception {
        String id=((Map<?,?>)batches.draft(new Draft("DEFECT","TEST",List.of(base().id()),"2024.02.29",List.of(),List.of(missing(1)),1,
            new Randomization("FIXED",null,null,"yyyy.MM.dd",4))).get("batch")).get("id").toString();
        Task task=store.tasks(id).getFirst();assertThat(task.params().baseDate()).isEqualTo("2024.02.29");
        assertThat(task.params().defect().positions()).doesNotContain(5,8);
    }
    @Test void unapprovedOrTestPoseCannotLeakIntoLiveRuns() throws Exception {
        Asset a=images.upload(png(),"POSE",DATE);images.region(a.id(),roi);
        assertThatThrownBy(()->draft(List.of(a.id()),List.of(missing(1)),1)).isInstanceOf(IllegalArgumentException.class);
        images.review(a.id(),new Review("APPROVED","normal","OK",""));store.jdbc().update("UPDATE asset SET source_type='TEST' WHERE id=?",a.id());
        assertThatThrownBy(()->batches.draft(new Draft("DEFECT","ACCOUNT",List.of(a.id()),DATE,List.of(),List.of(missing(1)),1))).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->images.region(a.id(),new Roi(.9,.2,.3,.2))).isInstanceOf(IllegalArgumentException.class);
    }
}
