package local.hamlab;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import java.io.IOException;
import java.net.URI;
import java.util.*;

/** Local-only UI rejects cross-site browser requests; no CORS wildcard or secret-bearing errors. */
@Component
public class HttpSafety implements Filter {
    public void doFilter(ServletRequest request,ServletResponse response,FilterChain chain) throws IOException,ServletException {
        HttpServletRequest req=(HttpServletRequest)request;HttpServletResponse res=(HttpServletResponse)response;
        String origin=req.getHeader("Origin");
        if(origin!=null) {
            try { URI uri=URI.create(origin); if(!Set.of("localhost","127.0.0.1","[::1]").contains(uri.getHost())) { res.sendError(403); return; } }
            catch(Exception e) { res.sendError(403);return; }
        }
        if("cross-site".equals(req.getHeader("Sec-Fetch-Site"))) { res.sendError(403); return; }
        if(!Set.of("GET","HEAD","OPTIONS").contains(req.getMethod()) && !"1".equals(req.getHeader("X-HamLab-Request"))) { res.sendError(403);return; }
        res.setHeader("X-Content-Type-Options","nosniff"); chain.doFilter(request,response);
    }
    /** Validation errors contain only local messages; unexpected errors deliberately omit payloads. */
    @RestControllerAdvice
    public static class Errors {
        @ExceptionHandler(IllegalArgumentException.class)
        ResponseEntity<Map<String,String>> invalid(IllegalArgumentException e) { return ResponseEntity.badRequest().body(Map.of("message",e.getMessage())); }
        @ExceptionHandler(Exception.class)
        ResponseEntity<Map<String,String>> unexpected(Exception e) { return ResponseEntity.status(500).body(Map.of("message","操作失败，请检查参数、文件、数据库和服务运行状态")); }
    }
}
