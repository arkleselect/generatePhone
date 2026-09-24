package local.hamlab;

import org.springframework.stereotype.Service;
import java.util.*;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Enumerates finite position coverage; appearance/severity remain configurable samples. */
@Service
public class DatasetPlans {
    public static final int LIMIT = 5000;
    private final RandomSamples samples;
    public DatasetPlans(RandomSamples samples) { this.samples=samples; }
    public record Sample(String date, Pose pose, Defect defect) {}

    /** Estimate uses the same expansion as creation; it never persists or submits tasks. */
    public List<Sample> expand(Draft d) {
        require(d.count()>=1 && d.count()<=LIMIT,"每组数量应为1至5000");
        List<Sample> result=new ArrayList<>();
        boolean coverage=d.coverage()!=null && !"RANDOM".equals(d.coverage().positions());
        if(coverage) {
            require("DEFECT".equals(d.stage()),"位置覆盖仅适用于日期缺陷");
            require(Set.of("ALL","CONTIGUOUS").contains(d.coverage().positions()),"位置覆盖方式无效");
            require(d.randomization()!=null,"请配置日期范围和格式");
            require(d.coverage().randomDates()>=0 && d.coverage().randomDates()<=100,"追加随机日期应为0至100个");
            Prompts.date(d.baseDate());
            // Complete one date before moving to the next; generated dates are distinct.
            List<String> dates=samples.uniqueDates(d.randomization(),d.baseDate(),d.coverage().randomDates());
            require(d.defects()!=null && !d.defects().isEmpty(),"缺陷配置不能为空");
            for(String date:dates) for(Defect defect:d.defects()) {
                require(defect!=null && Prompts.TYPES.contains(defect.type()),"缺陷类型无效");
                List<List<Integer>> combinations=Prompts.POSITION_TYPES.contains(defect.type())
                    ? positions(date,d.coverage().positions(),"multi_break".equals(defect.type())?2:1) : List.of(List.of());
                for(List<Integer> positions:combinations) for(int n=0;n<d.count();n++) {
                    Defect value=samples.defect(defect,date,d.randomization());
                    append(result,new Sample(date,null,new Defect(value.type(),positions,value.severity(),value.part(),value.direction(),value.object(),value.description())));
                }
            }
        } else {
            int variants="POSE".equals(d.stage()) ? (d.poses()==null?0:d.poses().size()) : (d.defects()==null?0:d.defects().size());
            require(variants>0,"配置不能为空");
            require((long)variants*d.count()<=LIMIT,"每批最多5000张，请减少日期或配置数量");
            for(int v=0;v<variants;v++) for(int n=0;n<d.count();n++) {
                String date=d.randomization()==null?d.baseDate():samples.date(d.randomization(),d.baseDate());
                Defect defect="DEFECT".equals(d.stage())?d.defects().get(v):null;
                if(defect!=null && d.randomization()!=null) defect=samples.defect(defect,date,d.randomization());
                append(result,new Sample(date,"POSE".equals(d.stage())?d.poses().get(v):null,defect));
            }
        }
        return result;
    }
    /** Bound expansion while constructing it to prevent huge user-controlled allocations. */
    private void append(List<Sample> result,Sample sample) {
        require(result.size()<LIMIT,"每批最多5000张，请减少日期或配置数量"); result.add(sample);
    }
    /** Numeric positions distinguish repeated digits; separators never become damage targets. */
    public List<List<Integer>> positions(String date,String mode,int minimum) {
        List<Integer> digits=new ArrayList<>();
        for(int i=0;i<date.length();i++) if(Character.isDigit(date.charAt(i))) digits.add(i+1);
        require(digits.size()>=minimum && digits.size()<=8,"完整覆盖支持最多8个数字的日期");
        List<List<Integer>> result=new ArrayList<>();
        for(int mask=1;mask<(1<<digits.size());mask++) {
            if(Integer.bitCount(mask)<minimum) continue;
            int shifted=mask>>>Integer.numberOfTrailingZeros(mask);
            if("CONTIGUOUS".equals(mode) && (shifted & (shifted+1))!=0) continue;
            List<Integer> selected=new ArrayList<>();
            for(int i=0;i<digits.size();i++) if((mask & (1<<i))!=0) selected.add(digits.get(i));
            result.add(List.copyOf(selected));
        }
        result.sort(Comparator.<List<Integer>>comparingInt(List::size).thenComparing(Object::toString));
        return result;
    }
}
