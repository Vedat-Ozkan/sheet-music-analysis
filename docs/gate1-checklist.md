# Gate 1 checklist: the test server in Claude and ChatGPT

Goal: see with real examples how a score file gets into each chat app and how the page comes back, so the owner can choose the display and upload approach.

The connector URL is the address in `out/tunnel.url` plus `/mcp`. It changes each time the tunnel is restarted (`spike/tunnel.sh start`); stop it with `spike/tunnel.sh stop`.

## Connect

**Claude** (claude.ai)
1. Customize > Connectors > Add custom connector.
2. Enter the connector URL. If asked about authentication, choose "No sign-in". Add.
3. In a new chat: + > Connectors, turn the connector on.

**ChatGPT** (chatgpt.com)
1. Settings > Security and login > turn on Developer mode. (Not every account has this option.)
2. Open chatgpt.com/plugins, select the plus button, give it a name and description, enter the connector URL under Connection, and create it.
3. In a new conversation, add the connection from the tools menu.

## Prompts

Run each in a fresh chat, in both apps. The file to attach is `tests/data/chopin_nocturne_op9_no2.mxl`.

| # | Prompt | What it tests |
|---|---|---|
| 1 | Show me the sample analysis. | Page out, as an inline image |
| 2 | Show me the sample analysis in a card. | Page out, in an in-chat card |
| 3 | *(attach the file)* Engrave bars 1–8 of the attached score. | File in, straight from the attachment |
| 4 | Give me an upload link for my score. *(upload the file there, then:)* My code is ______. Engrave bars 1–4. | File in, through an upload page |
| 5 | Engrave bars 1–8 of this score: https://raw.githubusercontent.com/musetrainer/library/master/scores/Chopin_-_Nocturne_Op_9_No_2_E_Flat_Major.mxl | File in, from a link |
| 6 | *(after prompt 4 gave you a code)* My code is ______. Analyse bars 1–8: draft the analysis, review it, and show me the annotated score with a short commentary. | The real loop: model draft, the chat model's review, annotated page |

Then repeat 1, 2 and 3 in each phone app.

## What to note for each

- Did the page appear in the chat, and was it readable without zooming?
- For prompt 3: what did the app do with the attachment, and how long did it take?
- A screenshot of each result.

The server logs which input path each call used (`out/spike/calls.log`), so that part needs no notes.

## Afterwards

Remove the connector in both apps (on Claude's Free plan it occupies the single custom-connector slot).
