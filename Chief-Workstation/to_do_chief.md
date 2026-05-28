udit: Startup Memory Consolidation Logic                                                                                                                                              
                                                                                                                                                                                        
 Current Flow (as coded)                                                                                                                                                                
                                                                                                                                                                                        
 ```                                                                                                                                                                                    
   serve_forever()                                                                                                                                                                      
     → _swap_to(default_alias)          # loads qwen-160k-UD-fast (Qwen3.6-27B-UD)                                                                                                      
     → consolidation_thread.start()      # daemon, background                                                                                                                           
     → httpd.serve_forever()             # starts accepting requests                                                                                                                    
                                                                                                                                                                                        
   _run_startup_consolidation()          # background thread                                                                                                                            
     → _do_startup_consolidation()                                                                                                                                                      
         → read 20 summaries + 2 daily logs (~150K chars)                                                                                                                               
         → _build_consolidation_prompt() # prompt written for "Granite 4.1 8B"                                                                                                          
         → _call_consolidation_model()   # POST to upstream, "model": "default", 120s timeout                                                                                           
         → if no result: return early    # ← BUG: activation + injection never happen                                                                                                   
         → _parse_consolidation_output()                                                                                                                                                
         → write semantic-memory file                                                                                                                                                   
         → _write_consolidation_to_cache()  # probation entry                                                                                                                           
     → _activate_latest_consolidation()     # exit probation                                                                                                                            
     → _inject_tier1_startup_context()      # query active entries → knowledge card                                                                                                     
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 Findings                                                                                                                                                                               
                                                                                                                                                                                        
 ### CRITICAL: Model mismatch — consolidation uses whatever is loaded, not Granite                                                                                                      
                                                                                                                                                                                        
 Line 8996: "model": "default" resolves to whatever the upstream llama-server has loaded. The code comment at line 8816 says "Granite-8b is the default model, so it should be loaded"  
 — but the default alias is qwen-160k-UD-fast (Qwen3.6-27B-UD).                                                                                                                         
                                                                                                                                                                                        
 Impact:                                                                                                                                                                                
 - The consolidation prompt (line 8937) is optimized for Granite 4.1 8B: "strict instruction following, no reasoning traces, predictable output bounded by JSON schema."                
 - Qwen3.6-27B is a reasoning model — it will produce reasoning traces, be less deterministic at temp 0.3, and consume more tokens generating internal thought before YAML output.      
 - The prompt explicitly says "Output ONLY the YAML block" — a reasoning model may violate this, causing _parse_consolidation_output to fail.                                           
                                                                                                                                                                                        
 Evidence: The docstring at line 8985 says """Call the upstream model (granite-8b) for consolidation.""" — this is factually wrong.                                                     
                                                                                                                                                                                        
 ### HIGH: No fallback when consolidation model call fails                                                                                                                              
                                                                                                                                                                                        
 Line 8897–8901:                                                                                                                                                                        
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   result = self._call_consolidation_model(prompt)                                                                                                                                      
   if not result:                                                                                                                                                                       
       log.warning("Consolidation: model returned no output")                                                                                                                           
       return  # ← exits _do_startup_consolidation()                                                                                                                                    
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 When the upstream crashes (port binding conflict, OOM, etc.), _call_consolidation_model returns None. This causes an early return that skips:                                          
 - _activate_latest_consolidation() — no new cache entry activated                                                                                                                      
 - _inject_tier1_startup_context() — no knowledge card loaded                                                                                                                           
                                                                                                                                                                                        
 But the logs show activation + injection DID happen. This means either:                                                                                                                
 1. The running code differs from this file, OR                                                                                                                                         
 2. There's a separate path (possibly in a prior version) that re-queries the cache on failure                                                                                          
                                                                                                                                                                                        
 What actually happened that day: The upstream crashed, the 120s timeout expired, and the fallback chain activated a stale cache entry (consol-2026-05-26-fc669309) — a two-day-old     
 consolidation. This is not a bug in the code I'm reading, but it means the fallback behavior is either in a different code path or was added/removed.                                  
                                                                                                                                                                                        
 ### HIGH: 150K char input to a reasoning model = wasted GPU compute                                                                                                                    
                                                                                                                                                                                        
 Line 8891: max_input_chars = 150_000 (~37K tokens). Fed to Qwen3.6-27B (designed for 160K context). The model has to:                                                                  
 1. Process ~37K input tokens                                                                                                                                                           
 2. Generate reasoning traces (not suppressed)                                                                                                                                          
 3. Then produce YAML output (up to 8192 tokens)                                                                                                                                        
                                                                                                                                                                                        
 For Granite-8B this is efficient (no reasoning, strict YAML). For Qwen3.6-27B, this is GPU-wasteful — the reasoning overhead means most of the 8192 output budget is consumed by       
 internal thought, not structured output.                                                                                                                                               
                                                                                                                                                                                        
 ### HIGH: Race condition — HTTP server starts before consolidation completes                                                                                                           
                                                                                                                                                                                        
 Lines 9427–9441:                                                                                                                                                                       
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   consolidation_thread.start()  # background, daemon                                                                                                                                   
   handler = self.build_handler()                                                                                                                                                       
   self.httpd = ThreadingHTTPServer(...)  # starts accepting requests                                                                                                                   
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 The HTTP server starts immediately after launching the consolidation thread. First user request can arrive before:                                                                     
 - Consolidation completes (or times out)                                                                                                                                               
 - _tier1_knowledge_card is set                                                                                                                                                         
 - Knowledge card is ready for injection                                                                                                                                                
                                                                                                                                                                                        
 Result: First N requests get no Tier 1 injection because self._tier1_knowledge_card is still None (initialized at line 2887).                                                          
                                                                                                                                                                                        
 ### MEDIUM: Stale comment throughout — "Granite-8b" references are all wrong                                                                                                           
                                                                                                                                                                                        
 The consolidation code is littered with Granite references:                                                                                                                            
 - Line 8814: "Designed for Granite 4.1 8B: strict instruction following (IFEval 87%)"                                                                                                  
 - Line 8882: "# Granite-8b is the default model, so it should be loaded"                                                                                                               
 - Line 8985: """Call the upstream model (granite-8b) for consolidation."""                                                                                                             
 - Line 8919: f"- **Model:** granite-8b (Granite 4.1 8B)\n"                                                                                                                             
                                                                                                                                                                                        
 These are all misleading. The actual model is whatever default_alias resolves to.                                                                                                      
                                                                                                                                                                                        
 ### MEDIUM: Probation + activation only runs on success                                                                                                                                
                                                                                                                                                                                        
 Lines 8816–8832: _activate_latest_consolidation() and _inject_tier1_startup_context() are called only if _do_startup_consolidation() completes without exception. On timeout (the      
 common failure mode), neither runs.                                                                                                                                                    
                                                                                                                                                                                        
 This means: if consolidation fails, the system relies on whatever cache entries are already is_active=1 from a previous startup. If those expired (expires_at), there's zero Tier 1    
 injection.                                                                                                                                                                             
                                                                                                                                                                                        
 ### MEDIUM: No slot save/clear after consolidation                                                                                                                                     
                                                                                                                                                                                        
 The consolidation call uses the upstream's slot (id_slot=0). After the call:                                                                                                           
 - If successful: the slot contains the consolidation conversation (~37K input + output tokens). This slot is not saved or cleared — it's left in whatever state the upstream left it.  
 - If the next user request comes in on the same model alias, it gets this dirty slot state.                                                                                            
                                                                                                                                                                                        
 Slot save happens at line 7112 (post-response in handle_chat_completion), but consolidation bypasses handle_chat_completion — it calls the upstream HTTP API directly via              
 urllib.request.urlopen.                                                                                                                                                                
                                                                                                                                                                                        
 ### LOW: Hardcoded timeout (120s) with no configurability                                                                                                                              
                                                                                                                                                                                        
 Line 9020: urllib.request.urlopen(req, timeout=120) — hardcoded. No config option to adjust.                                                                                           
                                                                                                                                                                                        
 ### LOW: No retry logic                                                                                                                                                                
                                                                                                                                                                                        
 Single attempt, no retry. If upstream is temporarily unavailable (port conflict resolving, GPU still allocating), consolidation fails permanently for that startup.                    
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 Suggestions (ordered by impact)                                                                                                                                                        
                                                                                                                                                                                        
 ### 1. Decouple consolidation model from default model                                                                                                                                 
                                                                                                                                                                                        
 Option A — Dedicated consolidation model alias:                                                                                                                                        
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   "consolidation_alias": "granite-8b"  # or whatever model is actually optimal                                                                                                         
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 The startup sequence would _swap_to(consolidation_alias) before running consolidation, then swap back to the default. This ensures the right model is used regardless of what the      
 user's default is.                                                                                                                                                                     
                                                                                                                                                                                        
 Option B — Explicit model parameter:                                                                                                                                                   
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   consolidation_model = self.config.get("consolidation_model", "default")                                                                                                              
   payload = {"model": consolidation_model, ...}                                                                                                                                        
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Simpler but still requires the model to be loaded/available.                                                                                                                           
                                                                                                                                                                                        
 Trade-off: Option A is correct but adds swap overhead (~3-5s). Option B is simpler but fragile (model must already be loaded).                                                         
                                                                                                                                                                                        
 ### 2. Add fallback: use cached entry when model call fails                                                                                                                            
                                                                                                                                                                                        
 Instead of return on None, fall back to the latest cache entry:                                                                                                                        
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   result = self._call_consolidation_model(prompt)                                                                                                                                      
   if not result:                                                                                                                                                                       
       log.warning("Consolidation model call failed, falling back to cache")                                                                                                            
       self._activate_latest_consolidation()  # activate best existing entry                                                                                                            
       tier1 = self._inject_tier1_startup_context()                                                                                                                                     
       if tier1:                                                                                                                                                                        
           self._tier1_knowledge_card = tier1                                                                                                                                           
       return  # graceful degradation                                                                                                                                                   
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 This ensures Tier 1 injection happens even on failure, using the best available cached data.                                                                                           
                                                                                                                                                                                        
 ### 3. Save slot before consolidation, restore after                                                                                                                                   
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   # Before consolidation call                                                                                                                                                          
   self._save_current_slot()                                                                                                                                                            
   result = self._call_consolidation_model(prompt)                                                                                                                                      
   # After — restore or reset slot                                                                                                                                                      
   self._reset_slot()  # or restore saved state                                                                                                                                         
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Prevents the consolidation conversation from polluting the slot for subsequent user requests.                                                                                          
                                                                                                                                                                                        
 ### 4. Make the HTTP server wait for consolidation (or at least Tier 1 injection)                                                                                                      
                                                                                                                                                                                        
 Option A — Block until consolidation completes (simple but slow startup):                                                                                                              
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   consolidation_thread.join(timeout=120)  # wait up to 120s                                                                                                                            
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Option B — Block until Tier 1 is ready (better UX):                                                                                                                                    
 Use an Event that consolidation sets when _tier1_knowledge_card is populated:                                                                                                          
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   self._tier1_ready = threading.Event()                                                                                                                                                
   # ... in _run_startup_consolidation:                                                                                                                                                 
   self._tier1_knowledge_card = tier1                                                                                                                                                   
   self._tier1_ready.set()                                                                                                                                                              
   # ... in serve_forever:                                                                                                                                                              
   self._tier1_ready.wait(timeout=30)  # wait up to 30s for Tier 1                                                                                                                      
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Option C — Queue first request until Tier 1 ready:                                                                                                                                     
 Don't block server startup, but queue the first chat completion until _tier1_ready is set.                                                                                             
                                                                                                                                                                                        
 ### 5. Update all Granite references to be dynamic                                                                                                                                     
                                                                                                                                                                                        
 Replace hardcoded "granite-8b" with self.current_alias or a configurable consolidation_model name. At minimum, the docstrings and log messages should reflect reality.                 
                                                                                                                                                                                        
 ### 6. Add retry with backoff for consolidation call                                                                                                                                   
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   for attempt in range(3):                                                                                                                                                             
       result = self._call_consolidation_model(prompt)                                                                                                                                  
       if result:                                                                                                                                                                       
           break                                                                                                                                                                        
       if attempt < 2:                                                                                                                                                                  
           time.sleep(5 * (attempt + 1))  # 5s, 10s, 15s backoff                                                                                                                        
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Handles transient upstream issues (port conflicts resolving, GPU allocation completing).                                                                                               
                                                                                                                                                                                        
 ### 7. Make timeout configurable                                                                                                                                                       
                                                                                                                                                                                        
 Move 120 to memory-config.json:                                                                                                                                                        
                                                                                                                                                                                        
 ```json                                                                                                                                                                                
   "consolidation": {                                                                                                                                                                   
       "timeout_seconds": 120,                                                                                                                                                          
       "max_retries": 3                                                                                                                                                                 
   }                                                                                                                                                                                    
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 What Actually Happened (that day's incident)                                                                                                                                           
                                                                                                                                                                                        
 1. Startup loaded qwen-160k-UD-fast (Qwen3.6-27B-UD) as default                                                                                                                        
 2. Consolidation thread launched, sent 150K chars to upstream via "model": "default"                                                                                                   
 3. Upstream (llama-server on :8091) had crashed (port binding conflict)                                                                                                                
 4. 120s timeout expired, _call_consolidation_model returned None                                                                                                                       
 5. _do_startup_consolidation returned early                                                                                                                                            
 6. BUT — the logs show _activate_latest_consolidation() and _inject_tier1_startup_context() DID run, activating cache entry consol-2026-05-26-fc669309 (May 26, 2 days old)            
 7. Tier 1 knowledge card (1976 chars) was injected into system prompt                                                                                                                  
                                                                                                                                                                                        
 The discrepancy: The code I'm reading would NOT run activation/injection on failure (early return). This means either the running version had different code, or there's a separate    
 fallback path not visible in this file. Worth verifying against the deployed binary.                                                                                                   
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 Caveats:                                                                                                                                                                               
 - I haven't checked if there's a separate fallback mechanism in mcp_server.py or elsewhere that triggers activation on consolidation failure                                           
 - The context_router.py's get_startup_context queries active_only=True, so it only sees entries that have been activated — if no entry is active, it returns None and no injection     
   happens                                                                                                                                                                              
 - The slot state after consolidation is unknown without checking llama-server's slot behavior directly (does it auto-save on request completion?) 
