# Windows本地开工与Git协作

目标：`D:\大三上\软件前沿技术\web3-agent-reputation`
预期远程：`https://github.com/Ryanjxy123/web3-agent-reputation.git`
本交接包没有访问该目录、修改remote、提交或push。共享网页未读取到仓库内容，以下必须由本地Codex按实际状态分支处理。

## 1. 先检查，不要先初始化
PowerShell：
```powershell
$Repo = 'D:\大三上\软件前沿技术\web3-agent-reputation'
if (Test-Path -LiteralPath $Repo) {
    Set-Location -LiteralPath $Repo
    Get-ChildItem -Force
    git rev-parse --show-toplevel
    git status --short --branch
    git remote -v
}
```
`git rev-parse`失败只说明当前目录不是Git工作树，不可把上级别的仓库误当本项目。注意检查顶层路径是否精确指向目标。
不要使用 `git reset --hard`、`git clean -fd`、强推、自动stash、覆盖已有.git、无提示搬走用户文件、或把不同工作树强行合并。

## 2. 按现状选择路径
### A. 本地尚不存在或为空，远程已有提交
优先在父目录clone，让远程历史自然进入本地：
```powershell
Set-Location -LiteralPath 'D:\大三上\软件前沿技术'
git clone https://github.com/Ryanjxy123/web3-agent-reputation.git web3-agent-reputation
Set-Location -LiteralPath 'D:\大三上\软件前沿技术\web3-agent-reputation'
```
再安装本规划包，保留已有README/LICENSE/.gitignore等；不要先制造另一套无关Git历史。
clone失败可能是登录/权限/网络，不是仓库为空。已有非空文件夹不要直接clone进去或删除重来。

### B. 本地已是正确仓库
检查remote与工作区。origin缺失时可添加：
```powershell
git remote add origin https://github.com/Ryanjxy123/web3-agent-reputation.git
```
已有origin若为等价SSH地址 `git@github.com:Ryanjxy123/web3-agent-reputation.git`，也视为正确，不必改。
origin指向其他仓库时停止remote写入；报告当前/预期给负责人，不自动替换。
```powershell
git ls-remote --symref origin HEAD
if ($LASTEXITCODE -ne 0) { throw '远程访问失败；不能当作空仓库继续。' }
git fetch --prune origin
```
不要把token嵌进URL、粘贴进文档或日志。使用Git Credential Manager、浏览器登录或已配置SSH；缺凭证继续独立本地开发，push明确标BLOCKED。

### C. 本地非空但没有.git
先盘点已有内容。用 `git ls-remote`确认远程状态；若远程已有历史，优先先clone到明确的新临时目录，再做逐文件比较/非覆盖合并，由负责人确认有冲突内容。
不能直接init后用 `--allow-unrelated-histories`掩盖不相干初始历史，更不能覆盖源文件。
若确认远程没有refs且读操作成功，才在目标目录：
```powershell
git init -b main
git remote add origin https://github.com/Ryanjxy123/web3-agent-reputation.git
```
第一条根提交是特殊bootstrap：可仅提交审过的README/现有许可/规划；负责人允许后push初始main，然后马上建功能分支。此例外不是之后可直接在main长期开发的许可。
未确认远程为空时不要执行这一组初始化。

## 3. 非覆盖安装交接包
压缩包展开后的目录是 `web3-agent-reputation-codex-kit`，其中 `repo` 是要放进项目的文件，外层安装器不属于应用源码。
PowerShell示例（把$Kit改成实际解压目录，不是仓库路径）：
```powershell
$Repo = 'D:\大三上\软件前沿技术\web3-agent-reputation'
$Kit = 'C:\Users\你的Windows用户名\Downloads\web3-agent-reputation-codex-kit'
py -3 "$Kit\install_plan.py" --target "$Repo" --on-conflict sidecar --dry-run
py -3 "$Kit\install_plan.py" --target "$Repo" --on-conflict sidecar
Set-Location -LiteralPath $Repo
py -3 scripts\check_bootstrap.py
py -3 scripts\git_doctor.py
```
没有`py`命令但有Python3时，可用`python`替换；若都未安装，先完成Python安装再跑参考测试。
安装器不覆盖不同内容：将incoming写到 `.bootstrap-incoming/<原相对路径>`。已有AGENTS.md时，Codex先读取现有规则与incoming，再手工合并；不能因为incoming存在就当新规则已经生效。
安装前后始终保留.git、原代码和用户未提交改动。安装器不是自动Git合并器，不修改远程，不运行代码安装命令。
不要把整包再套一层放到repo/plan/导致真正AGENTS不在仓库根目录。

## 4. 编码分支与提交
确认main已存在并更新（仅工作区干净时）：
```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/foundation-m0-m1
```
默认分支实际不是main时，使用实际默认分支；未经批准不改名。已有工作分支和未提交改动时不要强切，记录并保留。
每个小任务结束：
```powershell
git status --short
git diff --check
git diff
# 用实际明确路径暂存，不盲目git add .
git add AGENTS.md PLAN.md docs scripts configs packages tests fixtures .github .gitignore .gitattributes .editorconfig README.md
git diff --cached --stat
git diff --cached
# 先确认没有.env、私钥、运行证据包、数据库和身份信息
git commit -m "docs: add implementation contracts and bootstrap checks"
```
上述paths仅示例，实际不存在时不用；有用户原改动时只暂存本次明确创建/修改的文件或hunks，不能一起提交。
提交身份未配置时不得冒充负责人：记录 `git config --get user.name` / `user.email`状态，要求使用负责人真实或GitHub noreply身份，由用户设置本仓库local config；不写全局配置。
用户本次已表达维护远程协作意图；Codex只在remote匹配、认证可用、diff审查与测试通过时常规push当前工作分支：
```powershell
git push -u origin feat/foundation-m0-m1
```
不得替代负责人合并PR或直接push已有main。认证缺失不反复尝试，不把未push说成已同步。创建PR只有工具/认证实际可用时执行，否则输出分支、commit和PR说明草稿。

## 5. 负责人在GitHub完成的设置
按实际仓库可用功能配置：默认分支保护/Ruleset、通过PR合入、required checks、禁止强推/删除、邀请队友。私有仓库某些保护能力受产品方案影响，按当前界面确认，不宣称已配置。[S11]
CODEOWNERS已有负责人作为兜底，团队账号确认后再分目录；CODEOWNERS不会自动授予访问权限。
至少另一成员评审Schema/policy/合约/安全改动。不要设置“只能负责人审批”，同时又要求负责人给自己的PR审批——自己的PR不能以自己approval满足独立review；让队友进入对应owner/reviewer。
CI workflows默认read权限，不在pull_request_target执行不可信分支脚本，不把deploymentsecret给PR。
推荐PR squash或小规模逻辑merge；Git tag在验收通过的主分支commit建立，`v0.1.0-m1`等须核对不存在、由负责人确认发布。

## 6. Windows与WSL2
Codex可在适当Windows环境工作；涉及Foundry/Linux工具链时，Docker或WSL2通常更便于统一环境。[S12][S13]
项目路径含中文不需要改名；PowerShell用`-LiteralPath`和引号，Python用Path，不拼接未转义Shell字符串。
使用WSL2时同目录映射：
```bash
cd '/mnt/d/大三上/软件前沿技术/web3-agent-reputation'
```
在Windows/WSL只选择一处作为当前构建依赖环境；不要混用同一.venv/node_modules。Compose建议named volumes隔离Linux依赖。
首次镜像/依赖下载需要网络；准备完毕的local demo不应依赖8004scan、付费LLM或公网写链。

## 7. 每次交接必须报告
当前分支/HEAD、工作区是否clean、提交是否存在、push是否成功、测试真实结果、未跟踪文件、下一task_id。不要输出令牌/完整敏感remote URL。
远程验证命令、主分支保护与团队邀请是不同事情；绑定origin不等于已邀请队友，也不等于CI或分支保护已启用。
