**KungOS Local LLM Stack**  
**Overview**  
KungOS should default to a small, local-first stack built around an **8700G with 32GB DDR5** as the primary server profile, because that is the most realistic production target and it can run useful OCR, document parsing, embeddings, and office-assistant inference without requiring a discrete GPU. A practical architecture is to split the workload into four functions: document parsing, OCR/vision understanding, office-assistant inference, and embeddings/search.  
**Recommended default stack**  
The recommended default primary-server stack is:  
- **Primary server**: Ryzen 7 8700G, 32GB DDR5, no GPU, UMA frame buffer set to 8GB for the Radeon 780M iGPU.  
- **Document parser**: Docling as a CPU-sidecar for PDF and office-file extraction before LLM reasoning.  
- **OCR / visual document model**: Qwen2.5-VL-3B, preferably Q5_K_M on the 8700G 32GB profile.  
- **Office assistant model**: Granite 4.1-8B as the default assistant, with Qwen3-8B as the main alternative.  
- **Embeddings**: BGE-M3 INT8 for semantic search and retrieval.  
This split is better than trying to use one model for everything, because OCR-heavy document understanding and office-assistant tasks have different strengths and resource patterns.[web:40][web:87][web:89]  
**Model roles**  
| | | |  
|-|-|-|  
| **Function** | **Default model** | **Why it fits KungOS** |   
| Document parsing | Docling | Converts PDFs and office files into structured text and layout signals before inference, reducing load on the main model.[web:45][web:48] |   
| OCR / screenshots / invoices | Qwen2.5-VL-3B | Strong small VLM for document understanding and OCR-style tasks at a hardware level the 8700G can still handle.[web:40][web:75] |   
| Office assistant | Granite 4.1-8B | Very strong fit for long-document and RAG-style office workflows, with 512k context and much lower token output, which helps slower local hardware.[web:87][web:89][web:99] |   
| Alternate office assistant | Qwen3-8B | Better choice when stronger reasoning or more flexible instruction-following is needed.[web:82][web:86] |   
| Fast small fallback | Granite 4.1-3B | Good fallback for 16GB APU or very latency-sensitive use, with lower memory needs.[web:87][web:105] |   
| Embeddings / retrieval | BGE-M3 INT8 | Suitable for always-on semantic lookup without using GPU memory.[web:70] |   
   
**Hardware matrix**  
| | | | | |  
|-|-|-|-|-|  
| **Node type** | **Recommended hardware** | **OCR model** | **Assistant model** | **Notes** |   
| Default primary server | Ryzen 7 8700G + 32GB DDR5 | Qwen2.5-VL-3B Q5_K_M | Granite 4.1-8B Q4_K_M | Best realistic production default without a dGPU.[web:70][web:87][web:89] |   
| Lower-cost primary server | Ryzen 5 8600G + 32GB DDR5 | Qwen2.5-VL-3B Q4_K_M | Granite 4.1-3B or Qwen3-4B | Good if concurrency is light and responses can be a bit slower.[web:70][web:87] |   
| GPU-enabled branch / server | RX 6600 + Ryzen 7500F or 5500 | Qwen2.5-VL-3B Q5_K_M | Qwen3-8B or Granite 4.1-8B | Good balanced node if a small GPU is available.[web:74][web:82][web:89] |   
| Alternate small GPU server | RTX 3060 12GB | Qwen2.5-VL-3B or 7B | Qwen3.6-30B-A3B or Granite 4.1-8B | Best optional upgrade path if discrete GPU budget exists.[web:82][web:98][web:103] |   
| Low-power edge node | Mini PC / kiosk CPU-only | Granite-Docling-258M | Qwen3-0.6B | Best for lightweight scan-and-forward or simple assistant tasks.[web:37][web:84] |   
   
**Qwen3.6 and Granite 4.1 guidance**  
**Granite 4.1-8B** should be the default KungOS office-assistant model on APU-class hardware, because its long context window and lower token output make it more practical on slower local systems.[web:87][web:89][web:99]  **Qwen3-8B** should be kept as the alternate for tasks that benefit more from general instruction-following and reasoning flexibility.[web:82][web:86]  
**Qwen3.6-30B-A3B** is attractive because it activates only about 3B parameters at inference time, which gives it unusually high quality for its active compute footprint.[web:82][web:98] However, it is better treated as an optional upgrade for an RTX 3060 12GB node than as the baseline for an 8700G primary server, because the APU profile is still bandwidth-constrained and benefits more from simpler 8B-class models.[web:70][web:98]  
**Suggested production profile**  
For KungOS, the most practical production profile is:  
1. **8700G 32GB as the default primary server**.  
2. **Docling + Qwen2.5-VL-3B + Granite 4.1-8B + BGE-M3 INT8** as the default software stack.  
3. Add an **RX 6600** only if branch-local OCR or faster assistant response becomes necessary.[web:74][web:89]  
4. Consider an **RTX 3060 12GB** only if there is a clear need for Qwen3.6-class quality locally.[web:82][web:98][web:103]  
This keeps the stack realistic, local, inexpensive, and aligned with KungOS use cases such as invoice parsing, office-document assistance, reminders, CRM support, and inventory workflows.[cite:29][cite:30][cite:31]  
