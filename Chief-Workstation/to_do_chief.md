Now let me compile the findings:                                                                                                                                                       
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 What I learned:                                                                                                                                                                        
                                                                                                                                                                                        
 The SYCL backend has a cluster of known, unresolved issues that directly match your crash pattern. The community is actively hitting the same wall:                                    
                                                                                                                                                                                        
 1. The ggml_sycl_op_mul_mat crash at line 3093 is a known regression - Issue #24168 (https://github.com/ggml-org/llama.cpp/issues/24168) (Jun 2026) reports the exact same crash on    
 Intel Arc Pro B60 with hybrid/MoE architectures. The crash occurs during warmup mul_mat on SSM/GDN weights. The reporter found it was introduced between build 8477 (Mar 2026) and     
 build 9479 (Jun 2026). Your LFM2.5 MoE hits the same code path.                                                                                                                        
                                                                                                                                                                                        
 2. The reorder function crashes are actively being fixed - PR #24578 (https://github.com/ggml-org/llama.cpp/pulls/24578) (Jun 13, TODAY) fixes GGML_ASSERT(block_num_y % num_subgroups 
 == 0) crashes in the MMVQ reorder path. This addresses Issue #24304 (https://github.com/ggml-org/llama.cpp/issues/24304) (Qwen3-Embedding crashes) and Issue #24525                    
 (https://github.com/ggml-org/llama.cpp/issues/24525) (tensor split crashes in Q8_0 reorder). The fix rounds block_num_y up to the nearest multiple of num_subgroups instead of         
 asserting. This is likely related to your TG segfault at batch-size boundaries.                                                                                                        
                                                                                                                                                                                        
 3. llama-bench segfaults with SYCL is a known pattern - Issue #10850 (https://github.com/ggml-org/llama.cpp/issues/10850) reports that llama-bench segfaults after ggml_sycl_rms_norm  
 on SYCL/HIP while llama-cli works fine. The issue is that llama-bench uses larger batch sizes that trigger different kernel paths.                                                     
                                                                                                                                                                                        
 4. The DMMV/MMVQ reorder path has known gaps - Issue #21589 (https://github.com/ggml-org/llama.cpp/issues/21589) (Apr 2026) reports Qwen3.5 producing garbage on second prompt because 
 Q8_0 reorder support was added for DMMV/MMVQ (batch=1 TG path) but missed the GEMM dequantization path. This is exactly the batch-switch bug you're hitting.                           
                                                                                                                                                                                        
 5. MoE MUL_MAT_ID reorder support is incomplete - PR #24452 (https://github.com/ggml-org/llama.cpp/pulls/24452) (Jun 11) extends reordered MoE mul_mat_id to Q6_K. The PR notes that   
 Q4_K/Q5_K reorder was already supported, but Q6_K was missing. Your Q4_K_XL should be covered, but the MoE expert routing path may still have edge cases.                              
                                                                                                                                                                                        
 6. High ubatch crashes are a known SYCL limitation - Issue #23574 (https://github.com/ggml-org/llama.cpp/issues/23574) reports GLM 5.x crashing with high ubatch on SYCL. The root     
 cause is that dense KQ mask scales with n_kv * n_ubatch and can exceed backend indexing limits. The workaround dynamically caps ubatch per batch.                                      
                                                                                                                                                                                        
 7. Battlemage (your A380's architecture) has known SYCL performance issues - Issue #22413 (https://github.com/ggml-org/llama.cpp/issues/22413) reports SYCL on Battlemage B50/B70      
 running at "almost CPU speed" compared to Vulkan (3x slower PP, 3x slower TG). The community consensus is that Vulkan is more mature for Intel consumer GPUs.                          
                                                                                                                                                                                        
 8. Agentic use on Intel dGPUs is "totally broken" - Issue #18808 (https://github.com/ggml-org/llama.cpp/issues/18808) reports that SYCL on Arc Pro B50 stalls to single-digit PP after 
 context fills to 4k-8k tokens. GPU utilization spikes erratically. The user tried everything: FA on/off, different ub/b configs, q8_0 cache, different offloading strategies.          
                                                                                                                                                                                        
 Key takeaway: Your TG segfault at ub>20 is a SYCL backend bug in the MMVQ reorder path where block_num_y doesn't align with num_subgroups for certain batch sizes. PR #24578 (today)   
 fixes the assertion but may not fully resolve the segfault. The community workaround is GGML_SYCL_DISABLE_OPT=1 which disables the reorder optimization entirely (slower but stable).  
                                                                                                                                                                                        
 ────────────────────────────────────────────────────────────────────────────────                                                                                                       
                                                                                                                                                                                        
 ✅ All agents reported back!                                                                                                                                                           
 ├─ 🟠 Reddit: 12 threads │ 11,725 upvotes │ 2,826 comments                                                                                                                             
 ├─ 🟡 HN: 9 stories │ 51 points │ 6 comments                                                                                                                                           
 ├─ 🐙 GitHub: 1 item │ 116,408 reactions │ 1,862 comments                                                                                                                              
 └─ 🗣️ Top voices: r/LocalLLaMA, r/MachineLearning   
