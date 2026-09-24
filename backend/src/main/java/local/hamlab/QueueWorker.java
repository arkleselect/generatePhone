package local.hamlab;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.slf4j.LoggerFactory;
import java.util.concurrent.atomic.AtomicBoolean;
import static local.hamlab.Models.*;

/** Test work executes locally; account tasks wait for a real user-account result, one at a time. */
@Service
public class QueueWorker {
    private final Store store; private final Images images; private final Batches batches;
    private final TransactionTemplate tx; private final AtomicBoolean busy=new AtomicBoolean();
    public QueueWorker(Store store,Images images,Batches batches,TransactionTemplate tx) {
        this.store=store;this.images=images;this.batches=batches;this.tx=tx;
    }
    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        store.jdbc().update("UPDATE image_task SET status='UNKNOWN',error='处理过程因服务重启中断，请检查结果后再继续' WHERE status='RUNNING'");
    }
    @Scheduled(fixedDelayString="${app.queue-delay:1000}",initialDelayString="${app.queue-initial-delay:3000}")
    public void tick() {
        if(!busy.compareAndSet(false,true)) return;
        try {
            Task task=tx.execute(status -> claim());
            if(task!=null && task.status().equals("RUNNING")) test(task);
            store.jdbc().update("UPDATE batch SET status='COMPLETED' WHERE status='ACTIVE' AND NOT EXISTS (SELECT 1 FROM image_task t WHERE t.batch_id=batch.id AND t.status IN ('PENDING','RUNNING','AWAITING_IMAGE'))");
        } catch(Exception e) {
            LoggerFactory.getLogger(QueueWorker.class).error("队列状态持久化异常，请检查数据库和磁盘；不会自动重复提交任务");
        } finally { busy.set(false); }
    }
    private Task claim() {
        // The single outstanding account task survives restart and prevents repeated generation requests.
        if(store.jdbc().queryForObject("SELECT COUNT(*) FROM image_task WHERE status='AWAITING_IMAGE'",Integer.class)>0) return null;
        var active=store.jdbc().queryForList("SELECT * FROM batch WHERE status='ACTIVE' ORDER BY created_at LIMIT 1 FOR UPDATE");
        if(active.isEmpty()) return null;
        var batch=active.getFirst();
        var tasks=store.jdbc().query("SELECT * FROM image_task WHERE batch_id=? AND status='PENDING' ORDER BY sequence_no,created_at,id LIMIT 1 FOR UPDATE",store.taskMapper(),batch.get("id"));
        if(tasks.isEmpty()) return null;
        Task task=tasks.getFirst();
        try { batches.validateInput(store.asset(task.inputId()),(String)batch.get("stage"),(String)batch.get("mode")); }
        catch(IllegalArgumentException e) { store.jdbc().update("UPDATE image_task SET status='FAILED',error='参考图不再符合审核条件' WHERE id=?",task.id());return null; }
        String state="ACCOUNT".equals(batch.get("mode")) ? "AWAITING_IMAGE" : "RUNNING";
        store.jdbc().update("UPDATE image_task SET status=?,attempts=attempts+1 WHERE id=? AND status='PENDING'",state,task.id());
        return store.task(task.id());
    }
    private void test(Task task) {
        var batch=store.batch(task.batchId());
        try {
            byte[] result=images.testImage(store.asset(task.inputId()));
            tx.executeWithoutResult(status -> {
                try {
                    Asset output=images.generated(result,task,(String)batch.get("stage"),"TEST");
                    store.jdbc().update("UPDATE image_task SET status='SUCCEEDED',output_id=?,error=NULL WHERE id=?",output.id(),task.id());
                } catch(Exception e) { throw new IllegalStateException("测试结果保存失败"); }
            });
        } catch(Exception e) { store.jdbc().update("UPDATE image_task SET status='FAILED',error='测试图片生成或保存失败，请检查磁盘' WHERE id=?",task.id()); }
    }
}
