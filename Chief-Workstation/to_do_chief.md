/llm-wiki/Kung_OS/specs/endpoint_contract_spec_revised.md  Here's the completion summary:                                                                                              
                                                                                                                                                                                        
                                                                                                                                                                                        
  ✅ All Tasks Complete                                                                                                                                                                 
                                                                                                                                                                                        
                                                                                                                                                                                        
  ┌──────────┬───────────────────────────────────────────┬─────────────────┐                                                                                                            
  │ Priority │ Item                                      │ Status          │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P0       │ Remove legacy sessions/start from URLs    │ ✅ DONE         │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P1       │ Add bg_code to 3 get_collection() calls   │ ✅ DONE         │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P1       │ Remove refresh_token from JSON body       │ ✅ DONE         │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P1       │ Rename jwt_refresh → refresh_token cookie │ ✅ DONE         │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P2       │ Unify cafe_arcade get_tenant_context      │ ✅ Already done │                                                                                                            
  ├──────────┼───────────────────────────────────────────┼─────────────────┤                                                                                                            
  │ P2       │ Add branches to DivisionSerializer        │ ✅ DONE         │                                                                                                            
  └──────────┴───────────────────────────────────────────┴─────────────────┘                                                                                                            
                                                                                                                                                                                        
                                                                                                                                                                                        
  Files Modified                                                                                                                                                                        
                                                                                                                                                                                        
                                                                                                                                                                                        
 1. domains/cafe_arcade/urls.py — Removed sessions/start legacy route                                                                                                                   
                                                                                                                                                                                        
 2. domains/tournaments/views.py — Added bg_code to gettourdetails via resolve_minimal                                                                                                  
                                                                                                                                                                                        
 3. domains/shared/viewsets.py — Added bg_code to smsheadersapi and smsheaders_data_fetch callers                                                                                       
                                                                                                                                                                                        
 4. domains/shared/services.py — Added bg_code param to smsheaders_data_fetch                                                                                                           
                                                                                                                                                                                        
 5. users/api/viewsets.py — Removed refresh_token from JSON body + renamed jwt_refresh → refresh_token cookie (7 locations)                                                             
                                                                                                                                                                                        
 6. tenant/api/serializers.py — Added nested branches field to DivisionSerializer


Backend mixin + frontend migration (full spec compliance)                                                                                                                              
 - Create a FilterParserMixin that parses ?filter[field]=value into Django/Mongo filters                                                                                                
                                                                                                                                                                                        
 - Migrate all frontend calls to use ?filter[div_code]= format  
