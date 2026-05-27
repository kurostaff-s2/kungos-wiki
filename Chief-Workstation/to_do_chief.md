The per-model upstream_bin fields are dead config. They exist in the JSON but the code never reads them:                                                                               
                                                                                                                                                                                        
 1. Line 682-683: When parsing the JSON, upstream_bin gets dumped into a generic extra dict and discarded                                                                               
 2. Line 567-579: The ModelConfig dataclass has no upstream_bin field                                                                                                                   
 3. Line 2696: A single UpstreamProcess is created with the global --upstream-bin CLI arg and reused for every model                                                                    
                                                                                                                                                                                        
 So right now:                                                                                                                                                                          
                                                                                                                                                                                        
 ┌─────────────────────────────────────────────────────────────────────┬───────────────────────────────────────┐                                                                        
 │ What the config says                                                │ What actually happens                 │                                                                        
 ├─────────────────────────────────────────────────────────────────────┼───────────────────────────────────────┤                                                                        
 │ 4 models have "upstream_bin": "indras-mirror-fork/.../llama-server" │ Ignored — they use atomic-fork anyway │                                                                        
 ├─────────────────────────────────────────────────────────────────────┼───────────────────────────────────────┤                                                                        
 │ Global --upstream-bin = atomic-fork                                 │ This is the only binary used          │                                                                        
 └─────────────────────────────────────────────────────────────────────┴───────────────────────────────────────┘                                                                        
                                                                                                                                                                                        
 The crash happens because the atomic binary is the global binary, but the flag mapping code in super_council.py generates indras-mirror flag names (--spec-draft-n-max).               
                                                                                                                                                                                        
 Two ways to fix this:                                                                                                                                                                  
                                                                                                                                                                                        
 1. Quick fix — Update the flag mapping in super_council.py to use atomic binary flag names (--draft-max instead of --spec-draft-n-max). Everything works since atomic is the current   
    global binary.                                                                                                                                                                      
 2. Proper fix — Wire up per-model upstream_bin so models that need indras-mirror use it, and models needing nextn use atomic. This requires code changes to ModelConfig,               
    UpstreamProcess, and the model swap logic.  
    
    
    
    tx_checkpoints — not 0 for all models                                                                                                                                             
                                                                                                                                                                                        
 ┌────────────────────────┬───────┐                                                                                                                                                     
 │ Model                  │ Value │                                                                                                                                                     
 ├────────────────────────┼───────┤                                                                                                                                                     
 │ nemotron-cascade       │ 4     │                                                                                                                                                     
 ├────────────────────────┼───────┤                                                                                                                                                     
 │ gemma-4-26b-mtp        │ 8     │                                                                                                                                                     
 ├────────────────────────┼───────┤                                                                                                                                                     
 │ qwen3.6-27b-nextn      │ 8    
 
 
 
 
 
 
 "ctkd": "f16",                                                                                                                                                                 
         "ctvd": "f16",                                                                                                                                                                 
         "threads": 16,                                                                                                                                                                 
         "threads_batch": 16,                                                                                                                                                           
         "flash_attn": "on",                                                                                                                                                            
         "ctx_checkpoints": 8,                                                                                                                                                          
         "temp": 0.6,                                                                                                                                                                   
         "top_p": 0.95,                                                                                                                                                                 
         "top_k": 20
