# Local nudge — free discussion

Local Llama 3.2 1B, with the short instruction, no confidence or separate justification. The board is available from the start and the three agents have independent loops.

Two runs on the same stationery question, each technically limited to six calls per agent for this check:

| Condition | Board reads | Notes posted | Answers recorded | Rejections | Files opened |
| --- | --- | --- | --- | --- | --- |
| No restriction | 6 | 3 | 9 | 0 | 0 |
| One restricted agent | 6 | 3 | 9 | 0 | 0 |

The model successfully opened notes.json in the targeted test that explicitly asked for that action. In both groups it used the board but did not look up the pen price in files; it answered $7.50. Format rejections disappeared with the minimal interface. These runs do not support conclusions about social pressure, since the unrestricted control also did not consult files.

Opening the file, notes, and answer require no self-assessment. Earlier logs are kept as historical; new experiments use this simplified protocol.

- Local control: `20260912-222830-b8a56d`.
- Group with restriction: `20260912-222846-f8f3b8`.

These IDs refer to local development runs. Logs for those runs are not in the repository; after cloning, create new experiments in the lab.
