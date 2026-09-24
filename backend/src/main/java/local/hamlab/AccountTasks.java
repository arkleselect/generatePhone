package local.hamlab;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.zip.*;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Bridge for the current account's image tool or manual ChatGPT editing; no private browser APIs. */
@Service
public class AccountTasks {
    private final Store store; private final Images images;
    public AccountTasks(Store store,Images images) { this.store=store;this.images=images; }
    public Map<String,Object> next() {
        var pending=store.jdbc().query("SELECT * FROM image_task WHERE status='AWAITING_IMAGE' ORDER BY created_at LIMIT 1",store.taskMapper());
        if(pending.isEmpty()) return Map.of("available",false);
        Task task=pending.getFirst();Asset input=store.asset(task.inputId());
        return Map.of("available",true,"task",task,"reference_url","/api/assets/"+input.id()+"/file",
            "reference_path",images.file(input,false).toString(),"stage",store.batch(task.batchId()).get("stage"));
    }
    @Transactional
    public Asset complete(String id,byte[] bytes,String actualModel,String channel) throws IOException {
        require(actualModel!=null && actualModel.length()<=150,"实际模型记录过长");
        require(Set.of("MANUAL_CHATGPT","CODEX_IMAGE_TOOL","BROWSER_CHATGPT").contains(channel),"执行渠道无效");
        var locked=store.jdbc().queryForList("SELECT status FROM image_task WHERE id=? FOR UPDATE",id);
        // A human can recover a known result after an ambiguous submission; automatic imports cannot.
        String status=locked.isEmpty()?"":Objects.toString(locked.getFirst().get("status"),"");
        require(status.equals("AWAITING_IMAGE") || (status.equals("UNKNOWN") && channel.equals("MANUAL_CHATGPT")),
            "该任务不在等待图片状态，重复导入已阻止");
        Task task=store.task(id);String stage=(String)store.batch(task.batchId()).get("stage");
        Asset output=images.generated(bytes,task,stage,"ACCOUNT");
        store.jdbc().update("UPDATE image_task SET status='SUCCEEDED',output_id=?,actual_model=?,execution_channel=?,error=NULL WHERE id=?",
            output.id(),actualModel.isBlank()?null:actualModel,channel,id);
        return output;
    }
    @Transactional
    public void fail(String id,String reason,boolean uncertain) {
        require(reason!=null && !reason.isBlank() && reason.length()<=1000,"请填写失败原因");
        require(store.jdbc().update("UPDATE image_task SET status=?,error=? WHERE id=? AND status='AWAITING_IMAGE'",uncertain?"UNKNOWN":"FAILED",reason,id)==1,"任务不在等待图片状态");
    }
    /** Bundle is a transfer artifact, explicitly separate from the reviewed dataset export. */
    public void bundle(String id,OutputStream output) throws IOException {
        Task task=store.task(id);Asset input=store.asset(task.inputId());
        try(ZipOutputStream zip=new ZipOutputStream(output,StandardCharsets.UTF_8)) {
            entry(zip,"reference"+(input.filename().endsWith(".jpg")?".jpg":".png"),Files.readAllBytes(images.file(input,false)));
            entry(zip,"prompt.txt",task.prompt().getBytes(StandardCharsets.UTF_8));
            if(task.params().roi()!=null) entry(zip,"edit-region-mask.png",images.mask(input,task.params().roi()));
            entry(zip,"task.json",store.json().write(task).getBytes(StandardCharsets.UTF_8));
            entry(zip,"README.txt",("任务 "+task.id()+"\n请在你已登录的 ChatGPT 账号中上传 reference 图片并使用 prompt.txt。每个任务从本包参考图重新开始，不串联缺陷结果。\n遮罩仅用于指示编辑范围；账号界面不保证支持专用遮罩参数。生成后下载原图，在本系统此任务中导入。未知实际模型请留空，不编造。\n").getBytes(StandardCharsets.UTF_8));
        }
    }
    private void entry(ZipOutputStream zip,String name,byte[] bytes) throws IOException { zip.putNextEntry(new ZipEntry(name));zip.write(bytes);zip.closeEntry(); }
}
