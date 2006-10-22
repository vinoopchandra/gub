import misc
import os
        
class GitRepository:
    def __init__ (self, git_dir):
        self.repo_dir = git_dir
        self.system = misc.system
        self.read_pipe = misc.read_pipe
        self.checksums = {}
        
    def get_branches (self):
        branch_lines = self.read_pipe (self.git_command () + ' branch -l ').split ('\n')

        branches =  [b[2:] for b in branch_lines]
        return [b for b in branches if b]
        
        
    def git_command (self):
        cmd = 'git --git-dir ' + self.repo_dir
        return cmd
    
    def update (self, source, branch):
        cmd = self.git_command ()
        
        if os.path.isdir (self.repo_dir):
            refs = ' '.join ('%s:%s' % (b,b) for b in self.get_branches ())
            self.system ('%(cmd)s fetch %(source)s %(refs)s' % locals ())
        else:
            repo = self.repo_dir 
            self.system ('%(cmd)s clone --bare -n %(source)s %(repo)s' % locals ()) 

        self.checksums = {}
        
    def get_release_hash (self, branch):
        if self.checksums.has_key (branch):
            return self.checksums[branch]
        
        cs = self.read_pipe ('%s describe --abbrev=24 %s' % (self.git_command (),
                                                             branch))
        cs = cs.strip ()
        self.checksums[branch] = cs
        
        return cs

    def checkout (self, destdir, branch='master'):
        if not os.path.isdir (destdir):
            os.makedirs (destdir)

        cmd = self.git_command ()
        self.system ('cd %(destdir)s && %(cmd)s checkout %(branch)s' % locals())
     
        
