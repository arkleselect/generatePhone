package local.hamlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Cartesian expansion, explicit confirmation and state transitions share one persisted task model. */
@Service
public class Batches {
    private final Store store;
    private final Images images;
    private final Prompts prompts;
    private final ProviderConfig config;
    private final RandomSamples samples;
    private final DatasetPlans plans;
    public Batches(Store store, Images images, Prompts prompts, ProviderConfig config,RandomSamples samples,DatasetPlans plans) { this.store=store; this.images=images; this.prompts=prompts; this.config=config; this.samples=samples; this.plans=plans; }
    @Transactional
    public Map<String,Object> draft(Draft d) {
        require(d != null && Set.of("POSE","DEFECT").contains(d.stage()), "阶段无效");
        require(Set.of("TEST","ACCOUNT").contains(d.mode()), "调用模式无效"); if(d.randomization()!=null) samples.validate(d.randomization());
        if(d.randomization()==null || d.randomization().dateMode().equals("FIXED")) Prompts.date(d.baseDate());
        require(d.inputIds()!=null && !d.inputIds().isEmpty() && d.inputIds().size()<=100, "请选择1至100张输入图");
        require(new HashSet<>(d.inputIds()).size()==d.inputIds().size(), "输入图重复");
        var planned=plans.expand(d);
        require((long)d.inputIds().size()*planned.size()<=DatasetPlans.LIMIT,"每批最多5000张，请减少日期或配置数量");
        String batch=UUID.randomUUID().toString();
        store.jdbc().update("INSERT INTO batch(id,stage,status,mode) VALUES(?,?,'DRAFT',?)",batch,d.stage(),d.mode());
        int sequence=0;
        int inkLocationIndex=0;
        // Date-major order ensures complete coverage before moving on to another date.
        for(var sample:planned) for(String id:d.inputIds()) {
            Asset input=store.asset(id); validateInput(input,d.stage(),d.mode(),sample.defect());
            if(d.stage().equals("DEFECT") && d.randomization()==null)
                require(input.baseDate().equals(sample.date()),"底图日期与任务日期不一致，请使用新的日期采样配置");
            Params p=new Params(sample.date(),sample.pose()==null?input.pose():sample.pose(),sample.defect(),
                d.stage().equals("DEFECT")?input.roi():null,d.randomization());
            String prompt=prompts.build(d.stage(),p,input.role().equals("DEFECT_REF"),inkLocationIndex)+"\n画幅偏好："+config.settings().size()+"。实际输出尺寸以生成文件为准。";
            if(sample.defect()!=null && "ink_transfer".equals(sample.defect().type())) inkLocationIndex++;
            insert(batch,input,p,prompt,config.settings(),++sequence);
        }
        return detail(batch);
    }
    /** Only an approved matching reference may carry an existing defect into a new generation. */
    public void validateInput(Asset input,String stage,String mode,Defect defect) {
        if(stage.equals("POSE")) require(input.role().equals("SOURCE"), "姿势生成只接受原始参考图");
        else {
            require(java.util.Set.of("POSE","DEFECT_REF").contains(input.role()) && input.review().equals("APPROVED"),"缺陷生成必须使用已审核通过的底图或缺陷参考图");
            Prompts.roi(input.roi());
            if(input.role().equals("DEFECT_REF")) require(defect!=null && defect.type().equals(input.label()),"缺陷参考图只能生成相同缺陷类别");
        }
        require(!mode.equals("ACCOUNT") || !input.sourceType().equals("TEST"),"测试图片不能用于账号生图");
    }
    private void insert(String batch,Asset input,Params p,String prompt,Settings settings,int sequence) {
        store.jdbc().update("INSERT INTO image_task(id,batch_id,input_id,root_source_id,status,params_json,prompt,settings_json,sequence_no) VALUES(?,?,?,?,'DRAFT',?,?,?,?)",
            UUID.randomUUID().toString(),batch,input.id(),input.rootSourceId(),store.json().write(p),prompt,store.json().write(settings),sequence);
    }
    public Map<String,Object> detail(String id) { return Map.of("batch",store.batch(id),"tasks",store.tasks(id)); }
    @Transactional
    public void delete(String id) {
        var batch=lock(id);
        require(!"ACTIVE".equals(batch.get("status")),"请先暂停或取消批次再删除");
        require(store.jdbc().queryForObject("SELECT COUNT(*) FROM image_task WHERE batch_id=? AND status IN ('RUNNING','AWAITING_IMAGE','UNKNOWN')",Integer.class,id)==0,
            "批次含执行中或结果待核实的任务，请先处理结果再删除");
        require(store.jdbc().queryForObject("SELECT COUNT(*) FROM image_task t WHERE t.batch_id=? AND (t.output_id IS NOT NULL OR EXISTS (SELECT 1 FROM asset a WHERE a.task_id=t.id))",Integer.class,id)==0,
            "批次已有生成图片，需保留任务来源记录，不能删除");
        store.jdbc().update("DELETE FROM image_task WHERE batch_id=?",id);
        store.jdbc().update("DELETE FROM batch WHERE id=?",id);
    }
    /** Delete this batch's results and records while preserving shared input images. */
    @Transactional
    public void purge(String id) {
        var batch=lock(id);
        require(!"ACTIVE".equals(batch.get("status")),"请先暂停或取消批次再删除");
        require(store.jdbc().queryForObject("SELECT COUNT(*) FROM image_task WHERE batch_id=? AND status IN ('RUNNING','AWAITING_IMAGE','UNKNOWN')",Integer.class,id)==0,
            "批次含执行中或结果待核实的任务，请先处理结果再删除");
        List<String> ids=store.jdbc().queryForList("SELECT id FROM asset WHERE task_id IN (SELECT id FROM image_task WHERE batch_id=?) FOR UPDATE",String.class,id);
        List<Asset> outputs=new ArrayList<>();
        for(String outputId:ids) {
            Asset output=store.asset(outputId);
            Integer uses=store.jdbc().queryForObject("SELECT COUNT(*) FROM image_task WHERE batch_id<>? AND (input_id=? OR root_source_id=?)",Integer.class,id,outputId,outputId);
            Integer children=store.jdbc().queryForObject("SELECT COUNT(*) FROM asset WHERE id<>? AND (root_source_id=? OR parent_pose_id=?)",Integer.class,outputId,outputId,outputId);
            require(uses==0 && children==0,"批次图片 "+outputId.substring(0,8)+" 已被其他任务引用，不能删除");
            outputs.add(output);
        }
        store.jdbc().update("DELETE FROM image_task WHERE batch_id=?",id);
        for(Asset output:outputs) {
            store.jdbc().update("DELETE FROM asset WHERE id=?",output.id());
            images.deleteFilesAfterCommit(output);
        }
        store.jdbc().update("DELETE FROM batch WHERE id=?",id);
    }
    private Map<String,Object> lock(String id) {
        return store.jdbc().queryForList("SELECT * FROM batch WHERE id=? FOR UPDATE",id).stream().findFirst().orElseThrow(()->new IllegalArgumentException("批次不存在"));
    }
    @Transactional
    public void confirm(String id,Confirm body) {
        var batch=lock(id); require("DRAFT".equals(batch.get("status")),"只有草稿可确认，重复提交已阻止");
        require(body.confirmed(),"需要明确确认预计调用次数");
        List<Task> tasks=store.tasks(id);
        require(body.prompts()!=null && body.prompts().size()==tasks.size(),"提示词清单不完整");
        Map<String,String> edits=new HashMap<>();
        for(PromptEdit edit:body.prompts()) {
            require(edit.prompt()!=null && !edit.prompt().isBlank() && edit.prompt().length()<=16000,"提示词不能为空或超过16000字符");
            require(edits.put(edit.id(),edit.prompt())==null,"任务编号重复");
        }
        for(Task task:tasks) {
            require(edits.containsKey(task.id()),"任务编号不匹配");
            Asset input=store.asset(task.inputId());
            validateInput(input,(String)batch.get("stage"),(String)batch.get("mode"),task.params().defect());
            store.jdbc().update("UPDATE image_task SET prompt=?,status='PENDING' WHERE id=?",edits.get(task.id()),task.id());
        }
        store.jdbc().update("UPDATE batch SET status='ACTIVE' WHERE id=?",id);
    }
    @Transactional
    public void action(String id,String action) {
        var batch=lock(id); String status=(String)batch.get("status");
        switch(action) {
            case "pause" -> { require(status.equals("ACTIVE"),"批次未执行"); store.jdbc().update("UPDATE batch SET status='PAUSED' WHERE id=?",id); }
            case "resume" -> { require(status.equals("PAUSED"),"批次未暂停"); store.jdbc().update("UPDATE batch SET status='ACTIVE' WHERE id=?",id); }
            case "cancel" -> {
                store.jdbc().update("UPDATE batch SET status='CANCELLED' WHERE id=?",id);
                store.jdbc().update("UPDATE image_task SET status='CANCELLED' WHERE batch_id=? AND status IN ('DRAFT','PENDING')",id);
            }
            case "retry" -> {
                require(!status.equals("DRAFT"),"草稿尚未提交");
                int changed=store.jdbc().update("UPDATE image_task SET status='PENDING',error=NULL WHERE batch_id=? AND status='FAILED' AND attempts<3",id);
                require(changed>0,"没有可重试的失败任务（最多3次尝试）");
                store.jdbc().update("UPDATE batch SET status='ACTIVE' WHERE id=?",id);
            }
            default -> throw new IllegalArgumentException("批次操作无效");
        }
    }
    /** Unknown requests require explicit external verification before becoming retryable. */
    @Transactional
    public void resolveUnknown(String taskId,boolean verifiedNotAccepted) {
        require(verifiedNotAccepted,"请先核实账号中未生成结果；否则保留待确认状态");
        require(store.jdbc().update("UPDATE image_task SET status='FAILED',error='人工确认没有生成结果，可手动重试' WHERE id=? AND status='UNKNOWN'",taskId)==1,"任务不是待确认状态");
    }
    @Transactional
    public Map<String,Object> regenerate(String taskId) {
        Task task=store.task(taskId); var original=store.batch(task.batchId());
        String id=UUID.randomUUID().toString();
        validateInput(store.asset(task.inputId()),(String)original.get("stage"),(String)original.get("mode"),task.params().defect());
        store.jdbc().update("INSERT INTO batch(id,stage,status,mode) VALUES(?,?,'DRAFT',?)",id,original.get("stage"),original.get("mode"));
        insert(id,store.asset(task.inputId()),task.params(),task.prompt(),task.settings(),1); return detail(id);
    }
}
