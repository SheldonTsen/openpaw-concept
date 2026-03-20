
I want to build something like openclaw, but using Temporal.

It is important because then I get full visibility into the system of every thing the agent is doing. Yet, the system will keep going.

I know there's a few things that I want:

* Be able to run bash commands (probably via activities). Or perhaps leveraging the pydantic AI native integration with Temporal. 
* We can probably leverage temporal queues to have parallel "agents" working. 
* Heart beat - there must be a heart beat mechanism that prompts what to do every X minutes. This should be configurable prompt. I'm not sure whether this should be via signals in temporal, or each time it triggers a new workflow. 
* I think each agent that is called (how, not sure yet), will be able to modify it's state.md file. This is how we can have persistent memory across workflows or agent sessions(?)
* We need a way to run webhooks so that we can interact with the agent via slack or other channels.
* Activities - Just focus on running bash. We can install all sorts of CLIs on the worker to run. But I am a bit worried about is that temporal might block me from running os level commands. 
* I want to stop these agentic workflows every X frequency, so that the UI doesn't show something so long that it breaks. We can share memory across runs via state.md. WHich means we will have an external cronjob just starting these workflows, signals to make it do something, and then after X period, the workflow ends itself. Then the cronjob kicks start it again after that. This way in the UI we can see each long running session for each period. 

Unsure - need to think more:
* Sequential - in order to not end up with messy race conditions. Maybe we can have 1 agent as a long running workflow. Using signals to inject prompts to give the LLM direction of what to do. And I guess after each action, it has to modify its state.md file.  If they are sequential, we won't run into race conditions,
* This might mean several concurrent running workflows, needs parallel / independent folders. 
* Routing - Openclaw has some sort of routing mechanism, which determins which agent to route to. This is apparently simple, so we need to keep things simple. 
* Signal adaptor - for now let's just focus on potentially slack or email - somehow we should be able to send signals into the running workflow mid way (which implies the workflow might have some sort of wait). This might necessitate some sort of gateway server?



Codebase
* I want this whole system to run via docker compose - because I need the temporal server and ui.
* Will need a dockerfile for the worker
* Temporal workflows that achieve the above.
* Activities
* Think about some small tests we can potentially do. 
* Codebase needs to be written in python
* We need a way to be able to handle multiple LLM api keys, probably a llm.py file with all the different providers configured.


Task:
1. Inspect the openclaw repo under openclaw/openclaw - read the README then explore the src/ folder to get an idea of how it works. We will need to map concepts to temporal.
2. Come up with a plan.md but do not write any code. Describe the architecture, the components, the file layouts, schemas, pseudo code interfaces describing the entire system. Probably a high level diagram for architecture, followed by a potential implementation plan, and a testing strategy. Ensure to leave enough detail so someone can implement this in the future. 