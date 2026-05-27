### 1. Cherry-Pick vs Full Adoption — Unanimous: Cherry-Pick                                                                                                                           
                                                                                                                                                                                        
 All three agree. The reasoning converges on three points:                                                                                                                              
                                                                                                                                                                                        
 ┌──────────────────────────┬─────────────────────────────────┬─────────┬─────────┐                                                                                                     
 │ Concern                  │ Gemma                           │ Nemo    │ GPT     │                                                                                                     
 ├──────────────────────────┼─────────────────────────────────┼─────────┼─────────┤                                                                                                     
 │ Tooling conflict         │ ✅ ce_subagent vs pi-subagents  │ ✅ Same │ ✅ Same │                                                                                                     
 ├──────────────────────────┼─────────────────────────────────┼─────────┼─────────┤                                                                                                     
 │ Memory model conflict    │ ✅ context_handoff vs memsearch │ ✅ Same │ ✅ Same │                                                                                                     
 ├──────────────────────────┼─────────────────────────────────┼─────────┼─────────┤                                                                                                     
 │ Orchestration philosophy │ ✅ Chair > subagent-managed     │ ✅ Same │ ✅ Same │                                                                                                     
 └──────────────────────────┴─────────────────────────────────┴─────────┴─────────┘                                                                                                     
                                                                                                                                                                                        
 Nemo's addition: The cherry-pick currently misses hard-gate checks that the full design has (tool restrictions, signature tracking, patch validation). These need to be built          
 ourselves in Phase 2.                                                                                                                                                                  
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 2. Chair-as-Orchestrator — Unanimous: Sound, but 5 Edge Cases Need Guarding                                                                                                        
                                                                                                                                                                                        
 All three agree the model is architecturally correct. Nemo identified specific edge cases:                                                                                             
                                                                                                                                                                                        
 ┌─────────────────────────────┬───────────────────────────────┬────────────────────────────────────────────────────────────┐                                                           
 │ Edge Case                   │ Risk                          │ Nemo's Fix                                                 │                                                           
 ├─────────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────────┤                                                           
 │ Flaky tests                 │ Chair accepts lucky pass      │ Run RED test twice with identical seed                     │                                                           
 ├─────────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────────┤                                                           
 │ Semantic-equivalent patches │ No-op wastes repair budget    │ Normalize patches (canonicalize whitespace) before hashing │                                                           
 ├─────────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────────┤                                                           
 │ Stale memsearch cascade     │ Skips RED→GREEN gating        │ Recall-then-Validate: re-run RED test on recalled code     │                                                           
 ├─────────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────────┤                                                           
 │ Parallel file races         │ Two workers corrupt same file │ File-level ownership per task                              │                                                           
 ├─────────────────────────────┼───────────────────────────────┼────────────────────────────────────────────────────────────┤                                                           
 │ Subagent tool bypass        │ bash writes outside scope     │ OS sandboxing or per-task worktrees                        │                                                           
 └─────────────────────────────┴───────────────────────────────┴────────────────────────────────────────────────────────────┘                                                           
                                                                                                                                                                                        
 GPT's creative alternative: Micro-Judgement Layer + Explicit Phase Tokens — a stateless "Judge" that validates phase tokens (small JSON objects) instead of parsing free-form text.    
 Faster, no hallucination risk.                                                                                                                                                         
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 3. memsearch Integration — Three New Angles Beyond Passive Indexing                                                                                                                
                                                                                                                                                                                        
 All three envision memsearch as an active participant, not just a search engine:                                                                                                       
                                                                                                                                                                                        
 ┌────────────────────────────────┬──────────────┬─────────────────────────────────────────────────────────────────────────────────┐                                                    
 │ Pattern                        │ Who          │ What                                                                            │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Pre-dispatch recall            │ Gemma        │ Query "past solutions for [module]" before dispatching builder                  │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Failure signature matching     │ Gemma + Nemo │ When GREEN fails, search memsearch for the error string → inject known fix      │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Adaptive prompt tuning         │ GPT          │ Feed recent failure signatures into system message: "Last time we saw X, try Y" │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Self-improving review criteria │ GPT          │ Store review pass-rates per agent; bias future agent selection                  │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Learning-from-repair cycles    │ GPT          │ Store each repair attempt + outcome; compute difficulty-score per file          │                                                    
 ├────────────────────────────────┼──────────────┼─────────────────────────────────────────────────────────────────────────────────┤                                                    
 │ Version-aware injection        │ GPT          │ Tag artifacts with branch/commit; filter recall to current branch               │                                                    
 └────────────────────────────────┴──────────────┴─────────────────────────────────────────────────────────────────────────────────┘                                                    
                                                                                                                                                                                        
 Nemo's critical warning: Without safeguards, memsearch becomes a shortcut that bypasses RED→GREEN gating. Mitigation:                                                                  
 - Recall-then-Validate: After recall, re-run RED test → must still FAIL                                                                                                                
 - Signature-anchored recall: Store failure signature with the patch; verify match                                                                                                      
 - Sanitize snippets: Reject shell metacharacters, eval(), exec()                                                                                                                       
 - Versioned index: Index by task_id + phase; prevent GREEN solutions from being used as RED baseline                                                                                   
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 4. What the Ideal Workstation Looks Like (6 Months)                                                                                                                                
                                                                                                                                                                                        
 GPT's vision (most forward-looking):                                                                                                                                                   
                                                                                                                                                                                        
 ┌────────────────────────────────────┬───────────────────────────────────────────────────────┐                                                                                         
 │ Feature                            │ Purpose                                               │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Live test runner + auto-patch      │ Continuous feedback, shuts down flakiness             │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Per-task git worktree              │ Isolation without Docker overhead                     │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Context-aware prompt builder       │ 512-token slice from memsearch, not full context dump │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Agent-level telemetry              │ Detect stale/repeated failures early                  │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Auto-persistence of "good patches" │ Growing curriculum for future tasks                   │                                                                                         
 ├────────────────────────────────────┼───────────────────────────────────────────────────────┤                                                                                         
 │ Dynamic token budget               │ Scale prompt size with task complexity                │                                                                                         
 └────────────────────────────────────┴───────────────────────────────────────────────────────┘                                                                                         
                                                                                                                                                                                        
 What's missing from current proposal (all three agree):                                                                                                                                
 1. Standardized phase-state machine — serialized JSON, not ad-hoc checks                                                                                                               
 2. Definite human fallback pathway — not just "escalate" but a clear UI/flow                                                                                                           
 3. Git-based rollback — worktree → validate → merge, not direct writes                                                                                                                 
 4. Structural diff for no-op detection — AST comparison, not string hash                                                                                                               
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 5. Anti-Patterns & Over-Engineering Risks                                                                                                                                          
                                                                                                                                                                                        
 ┌──────────────────────────────────┬────────────┬──────────────────────────────────────────────────────────────────────────┐                                                           
 │ Risk                             │ Source     │ Fix                                                                      │                                                           
 ├──────────────────────────────────┼────────────┼──────────────────────────────────────────────────────────────────────────┤                                                           
 │ Serialisation through single GPU │ All three  │ Use Tiny Council for parallel inference, Chair as lightweight dispatcher │                                                           
 ├──────────────────────────────────┼────────────┼──────────────────────────────────────────────────────────────────────────┤                                                           
 │ Dismiss/re-dispatch cycles       │ GPT        │ Subagent produces ready-to-apply diff; Chair commits in one step         │                                                           
 ├──────────────────────────────────┼────────────┼──────────────────────────────────────────────────────────────────────────┤                                                           
 │ Hard-coded tool lists            │ GPT        │ Dynamic tools.json loaded at runtime                                     │                                                           
 ├──────────────────────────────────┼────────────┼──────────────────────────────────────────────────────────────────────────┤                                                           
 │ No git-based rollback            │ GPT + Nemo │ Per-task worktree, merge only after validation                           │                                                           
 ├──────────────────────────────────┼────────────┼──────────────────────────────────────────────────────────────────────────┤                                                           
 │ Token budget over-estimation     │ GPT        │ Calibrate with real measurements                                         │                                                           
 └──────────────────────────────────┴────────────┴──────────────────────────────────────────────────────────────────────────┘                                                           
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 6. Recommended Nemo 5-Step Chair Gate                                                                                                                                              
                                                                                                                                                                                        
 Nemo proposed a concrete validation sequence (ordered for max damage detection, min overhead):                                                                                         
                                                                                                                                                                                        
 ```                                                                                                                                                                                    
   Step 1: Phase-ordering guard     — O(1), check phase_state.json                                                                                                                      
   Step 2: Tool-usage audit         — Linear in log size, grep for prohibited commands                                                                                                  
   Step 3: Git-diff phase constraint — O(N files), compare against per-phase whitelist                                                                                                  
   Step 4: Failure-signature & no-op — O(1), hash comparison                                                                                                                            
   Step 5: Test outcome verification — Run RED twice (stability), GREEN once                                                                                                            
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 If any step fails → Chair rejects with specific evidence (not just "FAIL"), re-dispatches with targeted correction prompt.                                                             
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ### 7. Council Consensus: What to Do Next                                                                                                                                              
                                                                                                                                                                                        
 ┌──────────┬─────────────────────────────────────────────────────────────────────────────┬──────────────┐                                                                              
 │ Priority │ Action                                                                      │ Source       │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P0       │ Copy TDD hard gates + stop-the-line rule into test-driven-development skill │ All three    │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P0       │ Implement Nemo's 5-step Chair gate (Phase 2)                                │ Nemo + Gemma │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P1       │ Add memsearch pre-dispatch recall with Recall-then-Validate                 │ All three    │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P1       │ Implement failure signature tracking + bounded repair N=3                   │ Nemo + GPT   │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P2       │ Per-task git worktree isolation                                             │ GPT + Nemo   │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P2       │ Patch normalization before hashing                                          │ Nemo + GPT   │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P3       │ Adaptive prompt tuning from memsearch                                       │ GPT          │                                                                              
 ├──────────┼─────────────────────────────────────────────────────────────────────────────┼──────────────┤                                                                              
 │ P3       │ Agent-level telemetry + difficulty scoring                                  │ GPT          │                                                                              
 └──────────┴─────────────────────────────────────────────────────────────────────────────┴──────────────┘                                                                              
                                                                                                                                                                                        
 Bottom line: Cherry-pick the prompt templates from super-pi, build the hard enforcement (Chair validator) ourselves, and turn memsearch from passive archive into active feedback      
 engine. This gives us super-pi's discipline without its tooling baggage, plus enforcement that super-pi itself lacks.  
