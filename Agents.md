eOffice : This application will be used by a bank to digitize its paper based flows like approvals and sanctions . This application will not connect with existing digital flows like CBS , LOS & HRMS , it's main purpose would be to create a paperless banking environment.

The flow would be :
1. Initiator ( Any Individual Staff can be initiator)
2. Recommender (Can be an Individual or  multiple users at different level)
3. Approver (Can be an Individual or  multiple users at different level)
4. Control (Can be an Individual or  multiple users at different level)

The structure of Bank is : 
1. Head Office (CO) 
2. Regional Office (RO)
3. Branches (BO)

The hierarchy of users is :
1. In Head Office
    Level 1 : Desk Officers 
    Level 2 : Senior Managers (Optional) [They can be approver / sanctioning ]
    Level 3 : Head of Departments [They can be approver / sanctioning / controlling authority]
    Level 4 : AGMs (Optional ) [They can be approver / sanctioning / controlling authority]
    Level 5 : GMs [They can be approver / sanctioning / controlling authority]
    Level 6 : Chairman [They can be approver / sanctioning / controlling authority]

    ##Committee Approach
    Committee 1 : It will be sanctioning authority with 4 Individuals (GMs & AGMs) 
    Committee 2 : It will be sanctioning authority with 4 Individuals (GMs & Chairman)

2. In Regional Office
    Level 1 : Desk Officers 
    Level 2 : Senior Managers (Optional) [They can be approver / sanctioning ]
    Level 3 : Regional Manager [They can be approver / sanctioning / controlling authority]
    
    ##Committee Approach
    Committee 1 : It will be sanctioning authority with 4 Individuals (RM & Other Members) 

3. In Branches
    Level 1 : 2nd Officers (Optional)
    Level 2 : Branch Managers [They can be approver / sanctioning ]
    
Any user can be initiator for the process.
Process can be initiated from Branch and end at any other Level .

Some process will have predefined path , but option to create a custom path should be avaialable.

For financial powers , each level has been delegated with some powers in different heads , there sould be a mapping table containing the delegation , while initiating the process it shoudl automatically create a path for approval based on financial powers.

To maintain integrity of document (PDF) incremental digital singing at stages above the level 1 (initiator) is proposed. 

The signed PDFs at different stages should be stored and final signed doument should be available to donwload , after completion of the flow the final signed document to sent to all the involved users over email.

The preferred tech stack would Backend : Python , Frontend : HTML + JS (Basic , Use Bootstrap) , Database : PostgreSQL 

The user have HYP 2003 digital signature tokens.


