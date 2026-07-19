# Integrate external safety evidence through immutable local files

Agent Incident Replay Lab and LLM Eval Lab exchange only a versioned Validation Report JSON file. LLM Eval Lab admits the file as untrusted input, computes its own canonical content digest, stores an immutable copy against one completed Evaluation Run, and includes the admitted evidence in later Release Decision snapshots.

The repositories do not share a database, internal package, runtime process, or network interface. LLM Eval Lab validates the producer contract and the shape of source fingerprints but does not re-execute the incident, reproduce the producer's semantic fingerprint algorithm, or claim signer identity. This keeps both products independently runnable and preserves an honest offline trust model at the cost of deliberate schema-version coordination.
