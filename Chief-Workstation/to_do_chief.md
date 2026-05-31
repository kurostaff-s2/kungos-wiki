The broken chain                                                                                                                                                                       
                                                                                                                                                                                        
 ```                                                                                                                                                                                    
   1. upsert_raw_session_memory(trace_id, raw_text)                                                                                                                                     
      → SQLite: (trace_id, date, source_file, raw_text, ...)                                                                                                                            
      → NO project_id, NO type, NO session_id                                                                                                                                           
                                                                                                                                                                                        
   2. _try_index_raw_memory(trace_id, raw_text)                                                                                                                                         
      → indexer.index_file(path, project_id="council-memory")                                                                                                                           
         → pms.index_file(path, project_id="council-memory", type_filter="doc")                                                                                                         
            → self._ms.index_file(path)  ← embeds chunks, upserts to Milvus                                                                                                             
            → self._tag_project(path, "council-memory")  ❌ FAILS                                                                                                                       
            → self._tag_type(path, "doc")                 ❌ FAILS                                                                                                                      
                                                                                                                                                                                        
   3. search(query, project_id="council-memory")                                                                                                                                        
      → results = self._ms.search(query)  ← returns ALL chunks (no project_id in Milvus)                                                                                                
      → filter: metadata.get("project_id") == "council-memory"  ← ALWAYS None → NO MATCH                                                                                                
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Client-side filtering doesn't work because project_id was never written to Milvus. The _tag_project() upsert fails → metadata is empty → filter matches nothing.                       
                                                                                                                                                                                        
 How to ensure project_id mapping                                                                                                                                                       
                                                                                                                                                                                        
 Option A: Fix _tag_project() (include all fields)                                                                                                                                      
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   def _tag_project(self, source, project_id):                                                                                                                                          
       rows = self._ms.store.query(f"chunk_hash IN {hashes}")  # fetch full rows                                                                                                        
       for row in rows:                                                                                                                                                                 
           row["project_id"] = project_id  # add metadata to existing row                                                                                                               
       self._ms.store._client.upsert(collection_name=..., data=rows)  # ✅ includes all fields                                                                                          
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Expensive (fetch + upsert) but works.                                                                                                                                                  
                                                                                                                                                                                        
 Option B: Pass project_id through initial embedding (requires memsearch patch)                                                                                                         
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   # In memsearch/core.py _embed_and_store():                                                                                                                                           
   records.append({                                                                                                                                                                     
       "chunk_hash": chunk_id,                                                                                                                                                          
       "embedding": embeddings[i],                                                                                                                                                      
       "content": chunk.content,                                                                                                                                                        
       "source": chunk.source,                                                                                                                                                          
       "project_id": project_id,  # ← add here                                                                                                                                          
       "type": type_filter,        # ← add here                                                                                                                                         
   })                                                                                                                                                                                   
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Cleanest — one upsert, metadata travels with embedding.                                                                                                                                
                                                                                                                                                                                        
 Option C: Store in SQLite, join on trace_id (no Milvus changes)                                                                                                                        
                                                                                                                                                                                        
 ```sql                                                                                                                                                                                 
   ALTER TABLE raw_session_memories ADD COLUMN project_id TEXT;                                                                                                                         
   -- Query: SELECT * FROM raw_session_memories WHERE project_id = ? AND is_indexed = 1                                                                                                 
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Then use trace_id to correlate with Milvus chunks via source field.                                                                                                                    
                                                                                                                                                                                        
 Option D: Drop project_id from Milvus entirely                                                                                                                                         
 Since all council-memory entries share the same collection, and filtering is client-side via SQLite metadata, skip Milvus tagging. Use SQLite as the metadata store, Milvus as pure    
 vector index. 
 
 
 
 Milvus Lite doesn't support adding fields to existing collections. Need to drop + recreate with patched schema.                                                                        
                                                                                                                                                                                        
 Plan: Option B — Embed-time metadata                                                                                                                                                   
                                                                                                                                                                                        
 Changes needed:                                                                                                                                                                        
                                                                                                                                                                                        
 1. memsearch/store.py — Add project_id + type fields to schema                                                                                                                         
 2. memsearch/core.py — Accept project_id, type_filter in index_file() → propagate to _embed_and_store()                                                                                
 3. memsearch_wrapper.py — Pass metadata through index_file() instead of post-hoc _tag_project()/_tag_type()                                                                            
 4. Drop + recreate collection with new schema                                                                                                                                          
 5. Re-index all 152 entries with metadata                                                                                                                                              
                                                                                                                                                                                        
 Schema change:                                                                                                                                                                         
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   schema.add_field(field_name="project_id", datatype=DataType.VARCHAR, max_length=256, nullable=True)                                                                                  
   schema.add_field(field_name="type", datatype=DataType.VARCHAR, max_length=64, nullable=True)                                                                                         
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Embedding flow:                                                                                                                                                                        
                                                                                                                                                                                        
 ```python                                                                                                                                                                              
   # In _embed_and_store():                                                                                                                                                             
   records.append({                                                                                                                                                                     
       "chunk_hash": chunk_id,                                                                                                                                                          
       "embedding": embeddings[i],                                                                                                                                                      
       "content": chunk.content,                                                                                                                                                        
       "source": chunk.source,                                                                                                                                                          
       "project_id": project_id,     # ← new                                                                                                                                            
       "type": type_filter,          # ← new                                                                                                                                            
       "heading": chunk.heading,                                                                                                                                                        
       "heading_level": chunk.heading_level,                                                                                                                                            
       "start_line": chunk.start_line,                                                                                                                                                  
       "end_line": chunk.end_line,                                                                                                                                                      
   })                                                                                                                                                                                   
 ```                                                                                                                                                                                    
                                                                                                                                                                                        
 Result: project_id and type travel with every chunk from embedding → upsert. No post-hoc tagging needed. Client-side filtering works because metadata is in Milvus.  
