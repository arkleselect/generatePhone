package local.hamlab;

import java.time.Instant;
import java.util.List;

/** Shared domain records: API responses deliberately have no credential fields. */
public final class Models {
    private Models() {}
    public record Roi(double x, double y, double width, double height) {}
    public record Annotation(String classId, Roi box) {}
    public record Pose(String kind, double angle, double shift, String description) {}
    public record Defect(String type, List<Integer> positions, String severity, String part,
                         String direction, String object, String description) {}
    public record Randomization(String dateMode, String startDate, String endDate, String format, int maxAffected) {}
    public record Params(String baseDate, Pose pose, Defect defect, Roi roi, Randomization randomization) {
        // Retain existing stored snapshots and fixed-parameter callers.
        public Params(String baseDate, Pose pose, Defect defect, Roi roi) { this(baseDate,pose,defect,roi,null); }
    }
    public record Settings(String provider, String baseUrl, String model, String size, String quality, int timeoutSeconds) {}
    public record Asset(String id, String rootSourceId, String parentPoseId, String role, String sourceType,
                        String filename, int width, int height, long fileSize, String baseDate, Pose pose,
                        Roi roi, List<Annotation> annotations, String review, String label, String quality, String rejectionReason,
                        String taskId, Instant createdAt) {}
    public record Task(String id, String batchId, String inputId, String rootSourceId, String status,
                       Params params, String prompt, Settings settings, int attempts, String error,
                       String providerRequestId, String outputId, Instant createdAt, String actualModel, String executionChannel) {}
    public record Coverage(String positions, int randomDates) {}
    public record Draft(String stage, String mode, List<String> inputIds, String baseDate,
                        List<Pose> poses, List<Defect> defects, int count, Randomization randomization, Coverage coverage) {
        public Draft(String stage,String mode,List<String> inputIds,String baseDate,List<Pose> poses,List<Defect> defects,int count,Randomization randomization) {
            this(stage,mode,inputIds,baseDate,poses,defects,count,randomization,null);
        }
        public Draft(String stage,String mode,List<String> inputIds,String baseDate,List<Pose> poses,List<Defect> defects,int count) {
            this(stage,mode,inputIds,baseDate,poses,defects,count,null);
        }
    }
    public record PromptEdit(String id, String prompt) {}
    public record Confirm(boolean confirmed, List<PromptEdit> prompts) {}
    public record Review(String status, String label, String quality, String reason) {}
    public record BatchReview(List<String> ids, String status, String reason) {}
}
