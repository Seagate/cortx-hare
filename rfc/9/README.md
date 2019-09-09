---
original-author: Pieter Hintjens <ph@imatix.com>
original-url: http://hintjens.com/blog:23
domain: gitlab.mero.colo.seagate.com
shortname: 9/PC3
name: Pedantic Code Construction Contract
status: raw
editor: Valery V. Vorotyntsev <valery.vorotyntsev@seagate.com>
---

The Pedantic Code Construction Contract (PC3) is an evolution of the
GitHub [Fork + Pull Model](https://help.github.com/en/articles/about-collaborative-development-models),
and the [ZeroMQ C4 process](https://rfc.zeromq.org/spec:42/C4),
aimed at providing an optimal collaboration model for commercial
software projects.  PC3 helps an organization build consistently good
software, cheaply, and rapidly.

## Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in
[RFC 2119](https://tools.ietf.org/html/rfc2119).

## 1. Goals

PC3 is meant to provide an optimal collaboration model for commercial
software projects.  Broadly, PC3 helps an organization build
consistently good software, cheaply, and rapidly.  It has these
specific goals:

1. To maximize the scale and diversity of the community around a
   project, by reducing the friction for new Contributors and creating
   a scaled participation model with strong positive feedbacks;

2. To relieve dependencies on key individuals by separating different
   skill sets so that there is a larger pool of competence in any
   required domain;

3. To allow the project to develop faster and more accurately, by
   increasing the diversity of the decision making process;

4. To support the natural life-cycle of project versions from
   experimental through to stable, by allowing safe experimentation,
   rapid failure, and isolation of stable code;

5. To reduce the internal complexity of project repositories, thus
   making it easier for Contributors to participate and reducing the
   scope for error;

6. To reduce the need for meetings, face-to-face presence, and timezone
   synchronization, by capturing knowledge more accurately;

7. To optimize the efficiency of worker resources, by using on-time
   self-assignment instead of up-front task allocation.

## 2. Design

### 2.1. Preliminaries

1. The project SHALL use the git distributed revision control system.

2. The project SHALL be hosted on github.com or equivalent, herein
   called the "Platform".

3. The project SHALL use the Platform issue tracker.

4. The project SHOULD have clearly documented guidelines for code style.

5. A "Contributor" is a person who wishes to provide a patch, being a
   set of commits that solve some clearly identified problem.

6. A "Maintainer" is a person who merges patches to the project.
   Maintainers are not developers; their job is to enforce process.

7. A "Reviewer" is a person who reviews patches and who has deep
   familiarity with the code base.

8. Contributors SHALL NOT have commit access to the repository unless
   they are also Maintainers.

9. Maintainers SHALL have commit access to the repository.

10. Reviewers SHALL NOT have commit access to the repository unless they
    are also Maintainers.

11. Everyone, without distinction or discrimination, SHALL have an equal
    right to become a Contributor under the terms of this contract.

### 2.2. Patch Requirements

1. Maintainers, Contributors and Reviewers MUST have a Platform account
   and SHOULD use their real names or a well-known alias.

2. A patch SHOULD be a minimal and accurate answer to exactly one
   identified and agreed problem.

3. A patch MUST adhere to the code style guidelines of the project if
   these are defined.

4. A patch MUST adhere to the "Evolution of Public Contracts"
   guidelines defined below.

5. A patch MUST compile cleanly and pass project self-tests on at least
   the principal target platform.

6. A patch commit message MUST consist of a single short (less than 50
   characters ) line stating the problem ("Problem: ...") being solved,
   followed by a blank line and then the proposed solution
   ("Solution: ...").

7. A "Correct Patch" is one that satisfies the above requirements.

### 2.3. Development Process

1. Change on the project SHALL be governed by the pattern of accurately
   identifying problems and applying minimal, accurate solutions
   to these problems.

2. To request changes, a user SHOULD log an issue on the project
   Platform issue tracker.

3. The user or Contributor SHOULD write the issue by describing the
   problem they face or observe.

4. The user or Contributor SHOULD seek consensus on the accuracy of
   their observation, and the value of solving the problem.

5. Thus, the release history of the project SHALL be a list of
   meaningful issues logged and solved.

6. To work on an issue, a Contributor SHALL fork the project repository
   and then work on their forked repository.

7. To submit a patch, a Contributor SHALL create a Platform pull request
   back to the project.

8. A Contributor SHALL NOT commit changes directly to the project.

9. If the Platform implements pull requests as issues, a Contributor MAY
   directly send a pull request without logging a separate issue.

10. To discuss a patch, people MAY comment on the Platform pull request,
    on the commit, or elsewhere.

11. To accept or reject a patch, a Maintainer SHALL use the Platform
    interface.

12. Maintainers SHOULD NOT merge their own patches except in
    exceptional cases, such as non-responsiveness from other
    Maintainers for an extended period (more than 1-2 days).

13. Maintainers SHALL NOT make value judgments on correct patches,
    this is handled by the optional Code Review Process.

14. Maintainers SHOULD ask for improvements to incorrect patches and
    SHOULD reject incorrect patches if the Contributor does not
    respond constructively.

15. The user who created an issue SHOULD close the issue after
    checking the patch is successful.

16. Any Contributor who has value judgments on a patch SHOULD express
    these via their own patches.

17. Maintainers SHOULD close user issues that are left open without
    action for an uncomfortable period of time.

## 2.4. Code Review Process

1. The project MAY use a code review process, particularly if it is
   a shipping project with non-trivial complexity.

<!-- XXX What is a "shipping project"? -->

2. If code reviews are enabled for the project, Maintainers SHALL NOT
   merge a patch until a Reviewer has examined and approved the patch.

<!-- XXX
  -- - What does it take for code reviews to be disabled?
  --
  -- - Can code reviews be "enabled" for one pull request and
  --   "disabled" for another?
  -->

3. If code reviews are not enabled for the project, Maintainers SHALL
   merge correct patches from other Contributors rapidly.

### 2.5. Branches and Releases

<!-- Copied from https://rfc.zeromq.org/spec:42/C4/ -->

1. The project SHALL have one branch ("master") that always holds the
   latest in-progress version and SHOULD always build.

2. The project SHALL NOT use topic branches for any reason. Personal
   forks MAY use topic branches.

3. To make a stable release a Maintainer SHALL tag the repository.
   Stable releases SHALL always be released from the repository
   master.

<!-- XXX http://hintjens.com/blog:23 specifies this differently:
  --
  -- ## Creating Stable Releases
  --
  -- * The project SHALL have one branch ("master") that always holds the
  --   latest in-progress version and SHOULD always build.
  --
  -- * The project SHALL NOT use topic branches for any reason. Personal
  --   forks MAY use topic branches.
  --
  -- * To make a stable release someone SHALL fork the repository by
  --   copying it and thus become maintainer of this repository.
  --
  -- * Forking a project for stabilization MAY be done unilaterally and
  --   without agreement of project maintainers.
  --
  -- * Maintainers of the stabilization project SHALL maintain it through
  --   pull requests which MAY cherry-pick patches from the forked project.
  --
  -- * A patch to a repository declared "stable" SHALL be accompanied by a
  --   reproducible test case.
  --
  -- * A stabilization repository SHOULD progress through these phases:
  --   "unstable", "candidate", "stable", and then "legacy". That is, the
  --   default behavior of stabilization repositories is to die.
  -->

## 2.6. Evolution of Public Contracts

1. All Public Contracts (APIs or protocols) SHALL be documented.

2. All Public Contracts SHOULD have space for extensibility and
   experimentation.

3. A patch that modifies a stable Public Contract SHOULD not break
   existing applications unless there is overriding consensus on the
   value of doing this.

4. A patch that introduces new features to a Public Contract SHOULD
   do so using new names (a new contract).

5. New contracts SHOULD be marked as "draft" until they are stable and
   used by real users.

6. Old contracts SHOULD be deprecated in a systematic fashion by
   marking them as "deprecated" and replacing them with new contracts
   as needed.

7. When sufficient time has passed, old deprecated contracts SHOULD be
   removed.

8. Old names SHALL NOT be reused by new contracts.

9. When old names are removed, their implementations MUST provoke an
   exception (assertion) if used by applications.

## 2.7. Issue Format

1. One issue SHOULD address one single identifiable problem or a small
   set of tightly related problems.

2. The issue title SHOULD state the observed problem in minimal
   fashion.

3. The issue body SHOULD capture all relevant data in a minimal and
   accurate fashion.

4. The issue body MAY propose solutions.

5. Users SHALL NOT log feature requests, ideas, suggestions, or any
   solutions to problems that are not explicitly documented and
   provable.

## 2.8. Task and Role Assignment

1. All tasks and roles SHALL be self-assigned, based on individual
   judgement of the value of taking on a certain task or role.

<!--
## See also

* [Social Architecture 101](https://www.youtube.com/watch?v=uj-li0LO_2g)
  talk by Pieter Hintjens.  He describes the PC3 process at
  [\[38:52\]](https://www.youtube.com/watch?v=uj-li0LO_2g&t=38m52s).
-->
