package local.hamlab;

import org.springframework.stereotype.Service;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;
import static local.hamlab.Models.*;
import static local.hamlab.Prompts.require;

/** Resolve random sampling into concrete, immutable parameters before any image generation. */
@Service
public class RandomSamples {
    private static final Set<String> FORMATS=Set.of("yyyyMMdd","yyyy-MM-dd","yyyy.MM.dd");
    public void validate(Randomization r) {
        require(r!=null && r.dateMode()!=null && Set.of("RANDOM","FIXED").contains(r.dateMode()),"日期模式无效");
        require(r.format()!=null && FORMATS.contains(r.format()),"日期格式无效");
        require(r.maxAffected()>=2 && r.maxAffected()<=8,"自动影响字符数上限应为2至8");
        if(r.dateMode().equals("RANDOM")) {
            LocalDate start=parse(r.startDate()),end=parse(r.endDate());
            require(!end.isBefore(start) && ChronoUnit.DAYS.between(start,end)<=36600,"日期范围应按先后顺序，跨度不超过100年");
        }
    }
    private LocalDate parse(String value) {
        try { LocalDate date=LocalDate.parse(value);require(date.getYear()>=1900 && date.getYear()<=2199,"日期年份应在1900至2199之间");return date; }
        catch(Exception e) { throw new IllegalArgumentException("请填写1900至2199年间有效的日期范围"); }
    }
    public String date(Randomization r,String fixed) {
        if(r.dateMode().equals("FIXED")) { Prompts.date(fixed);return fixed; }
        LocalDate start=parse(r.startDate());long days=ChronoUnit.DAYS.between(start,parse(r.endDate()));
        return start.plusDays(ThreadLocalRandom.current().nextLong(days+1)).format(DateTimeFormatter.ofPattern(r.format()));
    }
    /** Sample dates without replacement and exclude the first date in all supported formats. */
    public List<String> uniqueDates(Randomization r,String first,int additional) {
        List<String> result=new ArrayList<>(); result.add(first);
        if(additional==0) return result;
        validate(new Randomization("RANDOM",r.startDate(),r.endDate(),r.format(),r.maxAffected()));
        LocalDate start=parse(r.startDate()), end=parse(r.endDate());
        List<String> pool=new ArrayList<>();
        for(LocalDate date=start;!date.isAfter(end);date=date.plusDays(1)) {
            String value=date.format(DateTimeFormatter.ofPattern(r.format()));
            if(!value.replaceAll("[^0-9]", "").equals(first.replaceAll("[^0-9]", ""))) pool.add(value);
        }
        require(pool.size()>=additional,"日期范围内没有足够的不重复日期");
        Collections.shuffle(pool); result.addAll(pool.subList(0,additional)); return result;
    }
    /** Select numeric characters only, never date separators; both contiguous and scattered damage occur. */
    public Defect defect(Defect d,String date,Randomization r) {
        require(d!=null && Prompts.TYPES.contains(d.type()),"缺陷类型无效");
        List<Integer> positions=List.of();
        if(Prompts.POSITION_TYPES.contains(d.type())) {
            List<Integer> digits=new ArrayList<>();
            for(int i=0;i<date.length();i++) if(Character.isDigit(date.charAt(i))) digits.add(i+1);
            int min=d.type().equals("multi_break")?2:1;
            require(digits.size()>=min,"当前日期中没有足够的数字供缺陷采样");
            int count=ThreadLocalRandom.current().nextInt(min,Math.min(r.maxAffected(),digits.size())+1);
            if(ThreadLocalRandom.current().nextBoolean()) Collections.shuffle(digits);
            else { int start=ThreadLocalRandom.current().nextInt(digits.size()-count+1);digits=new ArrayList<>(digits.subList(start,start+count)); }
            positions=digits.subList(0,count).stream().sorted().toList();
        }
        return new Defect(d.type(),positions,
            Prompts.SEVERITY_TYPES.contains(d.type())?choose(d.severity(),List.of("轻度","中度","重度")):"",
            choose(d.part(),List.of("上部","下部","左侧","右侧","局部笔画")),
            choose(d.direction(),List.of("左","右","上","下")),
            choose(d.object(),List.of("浅米色小碎屑","小片半透明薄膜","浅灰色纸屑")),d.description());
    }
    private String choose(String value,List<String> options) {
        return "随机".equals(value)?options.get(ThreadLocalRandom.current().nextInt(options.size())):value;
    }
}
