# Based on the ys theme by Yad Smood (Mar 2013)
# Extended to show active conda environment

# VCS
JJH_VCS_PROMPT_PREFIX1=" %{$reset_color%}on%{$fg[blue]%} "
JJH_VCS_PROMPT_PREFIX2=":%{$fg[cyan]%}"
JJH_VCS_PROMPT_SUFFIX="%{$reset_color%}"
JJH_VCS_PROMPT_DIRTY=" %{$fg[red]%}x"
JJH_VCS_PROMPT_CLEAN=" %{$fg[green]%}o"

# Git info
ZSH_THEME_GIT_PROMPT_PREFIX="${JJH_VCS_PROMPT_PREFIX1}git${JJH_VCS_PROMPT_PREFIX2}"
ZSH_THEME_GIT_PROMPT_SUFFIX="$JJH_VCS_PROMPT_SUFFIX"
ZSH_THEME_GIT_PROMPT_DIRTY="$JJH_VCS_PROMPT_DIRTY"
ZSH_THEME_GIT_PROMPT_CLEAN="$JJH_VCS_PROMPT_CLEAN"

# SVN info
ZSH_THEME_SVN_PROMPT_PREFIX="${JJH_VCS_PROMPT_PREFIX1}svn${JJH_VCS_PROMPT_PREFIX2}"
ZSH_THEME_SVN_PROMPT_SUFFIX="$JJH_VCS_PROMPT_SUFFIX"
ZSH_THEME_SVN_PROMPT_DIRTY="$JJH_VCS_PROMPT_DIRTY"
ZSH_THEME_SVN_PROMPT_CLEAN="$JJH_VCS_PROMPT_CLEAN"

# HG info
ys_hg_prompt_info() {
	# make sure this is a hg dir
	if [ -d '.hg' ]; then
		echo -n "${JJH_VCS_PROMPT_PREFIX1}hg${JJH_VCS_PROMPT_PREFIX2}"
		echo -n $(hg branch 2>/dev/null)
		if [[ "$(hg config oh-my-zsh.hide-dirty 2>/dev/null)" != "1" ]]; then
			if [ -n "$(hg status 2>/dev/null)" ]; then
				echo -n "$JJH_VCS_PROMPT_DIRTY"
			else
				echo -n "$JJH_VCS_PROMPT_CLEAN"
			fi
		fi
		echo -n "$JJH_VCS_PROMPT_SUFFIX"
	fi
}

# Virtualenv
local venv_info='$(virtenv_prompt)'
JJH_THEME_VIRTUALENV_PROMPT_PREFIX=" %{$fg[green]%}"
JJH_THEME_VIRTUALENV_PROMPT_SUFFIX=" %{$reset_color%}%"
virtenv_prompt() {
	[[ -n "${VIRTUAL_ENV:-}" ]] || return
	echo "${JJH_THEME_VIRTUALENV_PROMPT_PREFIX}${VIRTUAL_ENV:t}${JJH_THEME_VIRTUALENV_PROMPT_SUFFIX}"
}

# Conda environment
jjh_conda_prompt() {
	[[ -n "${CONDA_DEFAULT_ENV:-}" ]] || return
	[[ "${CONDA_DEFAULT_ENV}" == "base" ]] && return
	echo " %{$reset_color%}using %{$fg[magenta]%}conda:%{$fg[cyan]%}${CONDA_DEFAULT_ENV:t:gs/%/%%}%{$reset_color%}"
}

# Second line: vcs + conda (only shown if at least one is present)
local context_line='$(jjh_context_line)'
jjh_context_line() {
	# Call _omz_git_prompt_info directly to bypass oh-my-zsh's async
	# git prompt, which only activates when $(git_prompt_info) appears
	# literally in $PS1.
	local vcs=""
	(( $+functions[_omz_git_prompt_info] )) && vcs+="$(_omz_git_prompt_info)"
	(( $+functions[svn_prompt_info] )) && vcs+="$(svn_prompt_info)"
	(( $+functions[ys_hg_prompt_info] )) && vcs+="$(ys_hg_prompt_info)"
	local conda="$(jjh_conda_prompt)"
	[[ -n "$vcs" || -n "$conda" ]] || return
	print -rn "
%{$terminfo[bold]$fg[blue]%}#%{$reset_color%}${vcs}${conda}"
}

local exit_code="%(?,,C:%{$fg[red]%}%?%{$reset_color%})"

# Prompt format:
#
# [TIME] PRIVILEGES USER @ MACHINE in DIRECTORY C:LAST_EXIT_CODE
# on git:BRANCH STATE using conda:ENV
# $ COMMAND
#
PROMPT="
%{$terminfo[bold]$fg[blue]%}#%{$reset_color%} \
[%*] \
%(#,%{$bg[yellow]%}%{$fg[black]%}%n%{$reset_color%},%{$fg[cyan]%}%n) \
%{$reset_color%}@ \
%{$fg[green]%}%m \
%{$reset_color%}in \
%{$terminfo[bold]$fg[yellow]%}%~%{$reset_color%}\
${venv_info}\
 $exit_code\
${context_line}
%{$terminfo[bold]$fg[red]%}$ %{$reset_color%}"
